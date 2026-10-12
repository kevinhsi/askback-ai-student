#!/usr/bin/env python
"""AskBack AI Student — 執行入口。

子命令：
  units     列出可選學習單元與迷思
  student   產生 output/student_question.json
  tts       由 JSON 產生語音（output/student_voice.wav）
  animate   由 JSON + 語音產生動畫影片（output/student_animation.mp4）
  srt       產生字幕（output/student_subtitles.srt）
  all       完整管線（學生 → 語音 → 動畫 → 字幕 → 合成 → 驗證 → manifest）
  verify    驗證既有影片

範例：
  python main.py all
  python main.py all --unit sci-g6-circuit --provider sapi
  python main.py verify --video output/student_animation.mp4
"""

from __future__ import annotations

import argparse
import datetime as _dt
import hashlib
import json
import os
import platform
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional

ROOT = Path(__file__).resolve().parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from animation_generator import build_scene_script  # noqa: E402
from media_pipeline.compose import assemble_audio, render_and_mux  # noqa: E402
from media_pipeline.subtitles import build_srt  # noqa: E402
from media_pipeline.timeline import build_timeline  # noqa: E402
from media_pipeline.verify import verify_video  # noqa: E402
from student_simulator import build_student_question, list_misconceptions, list_units  # noqa: E402
from student_simulator.simulator import load_student_question  # noqa: E402
from tts_generator import available_providers, synthesize_lines  # noqa: E402
from tts_generator import audio as A  # noqa: E402

DEFAULT_OUT = ROOT / "output"
STUDENT_JSON = "student_question.json"
AUDIO_WAV = "student_voice.wav"
VIDEO_MP4 = "student_animation.mp4"
SUBTITLE_SRT = "student_subtitles.srt"
MANIFEST_JSON = "generation_manifest.json"


def _env_int(name: str, default: int) -> int:
    try:
        return int(os.environ.get(name, "") or default)
    except ValueError:
        return default


def _env_float(name: str, default: float) -> float:
    try:
        return float(os.environ.get(name, "") or default)
    except ValueError:
        return default


def _sha256(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


def _now() -> str:
    return _dt.datetime.now().astimezone().replace(microsecond=0).isoformat()


def _ffmpeg_version() -> str:
    exe = shutil.which("ffmpeg")
    if not exe:
        return "not found"
    try:
        out = subprocess.run([exe, "-version"], stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=30)
        return out.stdout.decode("utf-8", "replace").splitlines()[0]
    except Exception:  # noqa: BLE001
        return "unknown"


# ---------------------------------------------------------------------------
# 各階段
# ---------------------------------------------------------------------------
def cmd_units(_args: argparse.Namespace) -> int:
    print(json.dumps({"units": list_units()}, ensure_ascii=False, indent=2))
    return 0


def cmd_student(args: argparse.Namespace) -> Path:
    out = Path(args.out) / STUDENT_JSON
    replies = None
    if args.turns > 1:
        from student_simulator.simulator import DEFAULT_USER_PROMPTS

        replies = list(DEFAULT_USER_PROMPTS[: args.turns - 1])
    data = build_student_question(
        unit_id=args.unit,
        mc_index=args.mc,
        mode=args.mode,
        user_replies=replies,
        out_path=out,
    )
    print(f"[student] 已寫入 {out}")
    print(f"[student] 單元: {data['unit']['unit_name']} / 迷思: {data['misconception']['id']}")
    print(f"[student] 台詞 {len(data['question']['lines'])} 句 / 答案洩漏: "
          f"{data['safety']['answer_leak']['leaked']}")
    if data["generator"].get("fallback_reason"):
        print(f"[student] 備註: {data['generator']['fallback_reason']}")
    return out


def cmd_tts(args: argparse.Namespace) -> Dict[str, Any]:
    student_path = Path(args.student) if args.student else Path(args.out) / STUDENT_JSON
    data = load_student_question(student_path)
    cues_dir = Path(args.out) / "_cues"
    result = synthesize_lines(data["question"]["lines"], cues_dir, provider=args.provider)
    print(f"[tts] 引擎: {result['provider']}，共 {len(result['cues'])} 句，"
          f"語音總長 {result['total_duration']}s")
    for att in result["attempts"]:
        print(f"[tts]   - {att['provider']}: {att['error']}")
    return {"student": data, "tts": result, "cues_dir": cues_dir}


def build_timeline_and_audio(data: Dict[str, Any], tts_result: Dict[str, Any],
                             out_dir: Path) -> Dict[str, Any]:
    widths = _env_int("ASKBACK_VIDEO_WIDTH", 1280)
    height = _env_int("ASKBACK_VIDEO_HEIGHT", 720)
    fps = _env_int("ASKBACK_VIDEO_FPS", 24)
    tmin = _env_float("ASKBACK_TARGET_MIN", 30.0)
    tmax = _env_float("ASKBACK_TARGET_MAX", 90.0)
    hints = data["misconception"].get("line_hints") or []
    durations = [c["duration"] for c in tts_result["cues"]]
    timeline = build_timeline(
        durations,
        hints,
        fps=fps,
        width=widths,
        height=height,
        target_min=tmin,
        target_max=tmax,
    )
    cue_paths = [c["path"] for c in tts_result["cues"]]
    audio_info = assemble_audio(cue_paths, timeline, out_dir / AUDIO_WAV)
    return {"timeline": timeline, "audio": audio_info, "cue_paths": cue_paths}


def cmd_srt(data: Dict[str, Any], timeline: Dict[str, Any], out_dir: Path) -> Path:
    subs = [
        {
            "index": c["index"],
            "text": data["question"]["lines"][c["index"]],
            "start": c["subtitle_start"],
            "end": c["subtitle_end"],
        }
        for c in timeline["cues"]
    ]
    path = build_srt(subs, out_dir / SUBTITLE_SRT, field_start="start", field_end="end")
    print(f"[srt] 已寫入 {path}（{len(subs)} 條）")
    return path


def cmd_verify(args: argparse.Namespace) -> Dict[str, Any]:
    video = Path(args.video) if args.video else Path(args.out) / VIDEO_MP4
    tmin = _env_float("ASKBACK_TARGET_MIN", 30.0)
    tmax = _env_float("ASKBACK_TARGET_MAX", 90.0)
    result = verify_video(video, target_min=tmin, target_max=tmax)
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return result


def cmd_all(args: argparse.Namespace) -> int:
    out_dir = Path(args.out)
    out_dir.mkdir(parents=True, exist_ok=True)
    steps: List[Dict[str, Any]] = []
    warnings: List[str] = []

    # 1) 學生迷思 JSON
    student_path = cmd_student(args)
    data = load_student_question(student_path)
    steps.append({
        "step": "student_question",
        "status": "ok",
        "tool": "student_simulator (template/llm)",
        "output": str(student_path.relative_to(ROOT)) if student_path.is_relative_to(ROOT) else str(student_path),
        "details": {
            "unit_id": data["unit"]["unit_id"],
            "misconception_id": data["misconception"]["id"],
            "lines": len(data["question"]["lines"]),
            "generator_mode": data["generator"]["mode"],
            "answer_leak": data["safety"]["answer_leak"]["leaked"],
        },
    })

    # 2) TTS
    try:
        tts_bundle = cmd_tts(args)
    except Exception as exc:  # noqa: BLE001
        steps.append({"step": "tts", "status": "failed", "tool": "tts_generator",
                      "error": f"{type(exc).__name__}: {exc}"})
        _write_manifest(out_dir, steps, warnings, data)
        print(f"[tts] 失敗: {type(exc).__name__}: {exc}")
        return 2
    tts_result = tts_bundle["tts"]
    steps.append({
        "step": "tts",
        "status": "ok",
        "tool": f"tts_generator:{tts_result['provider']}",
        "output": str((out_dir / AUDIO_WAV).relative_to(ROOT)),
        "details": {
            "provider": tts_result["provider"],
            "engine": tts_result["provider"],
            "cue_count": len(tts_result["cues"]),
            "speech_total_seconds": tts_result["total_duration"],
            "failed_attempts": tts_result["attempts"],
            "intermediate_cues": str(tts_bundle["cues_dir"].relative_to(ROOT)),
        },
    })
    for att in tts_result["attempts"]:
        warnings.append(f"TTS 供應商 {att['provider']} 不可用（已改用 {tts_result['provider']}）: {att['error']}")

    # 3) 時間軸 + 語音組裝
    tl_bundle = build_timeline_and_audio(data, tts_result, out_dir)
    timeline = tl_bundle["timeline"]
    audio_info = tl_bundle["audio"]
    steps.append({
        "step": "audio_timeline",
        "status": "ok",
        "tool": "media_pipeline.timeline + tts_generator.audio(ffmpeg)",
        "output": str((out_dir / AUDIO_WAV).relative_to(ROOT)),
        "details": {
            "audio_duration": audio_info["duration"],
            "video_duration_planned": timeline["duration"],
            "scenes": len(timeline["scenes"]),
            "peak": audio_info["peak"],
            "rms": audio_info["rms"],
        },
    })

    # 4) 字幕
    srt_path = cmd_srt(data, timeline, out_dir)
    steps.append({
        "step": "subtitles",
        "status": "ok",
        "tool": "media_pipeline.subtitles",
        "output": str(srt_path.relative_to(ROOT)),
        "details": {"cues": len(timeline["cues"]), "encoding": "utf-8-sig"},
    })

    # 5) 動畫 + 合成
    script = build_scene_script(data, timeline)
    video_path = out_dir / VIDEO_MP4
    try:
        render_info = render_and_mux(script, out_dir / AUDIO_WAV, video_path)
    except Exception as exc:  # noqa: BLE001
        steps.append({"step": "animation", "status": "failed",
                      "tool": "animation_generator + ffmpeg",
                      "error": f"{type(exc).__name__}: {exc}"})
        _write_manifest(out_dir, steps, warnings, data)
        print(f"[animate] 失敗: {type(exc).__name__}: {exc}")
        return 3
    steps.append({
        "step": "animation_compose",
        "status": "ok",
        "tool": f"animation_generator(Pillow 程式化2D) + ffmpeg rawvideo 合成，{render_info['frames']} 影格",
        "output": str(video_path.relative_to(ROOT)),
        "details": {
            "frames": render_info["frames"],
            "fps": render_info["fps"],
            "resolution": f"{render_info['width']}x{render_info['height']}",
            "planned_duration": render_info["duration"],
            "file_bytes": render_info["bytes"],
            "audio_track": str((out_dir / AUDIO_WAV).relative_to(ROOT)),
        },
    })

    # 6) 驗證
    verification = verify_video(
        video_path,
        target_min=_env_float("ASKBACK_TARGET_MIN", 30.0),
        target_max=_env_float("ASKBACK_TARGET_MAX", 90.0),
    )
    # 字幕一致性驗證
    from media_pipeline.subtitles import parse_srt

    srt_entries = parse_srt(srt_path)
    sub_texts = [e["text"] for e in srt_entries]
    verification["subtitles_match_lines"] = sub_texts == data["question"]["lines"]
    verification["subtitle_count"] = len(srt_entries)
    steps.append({
        "step": "verification",
        "status": "ok" if verification.get("ok") else "failed",
        "tool": "ffprobe + ffmpeg volumedetect + frame sampling",
        "output": str(video_path.relative_to(ROOT)),
        "details": verification,
    })

    manifest = _write_manifest(out_dir, steps, warnings, data, verification)
    print(f"[done] 影片: {video_path}")
    print(f"[done] 長度: {verification['checks'].get('duration_seconds')}s "
          f"(目標 {verification['checks'].get('duration_in_range')})")
    print(f"[done] 驗證: ok={verification.get('ok')} / 字幕一致={verification.get('subtitles_match_lines')}")
    print(f"[done] manifest: {manifest}")
    return 0 if verification.get("ok") else 4


def _write_manifest(out_dir: Path, steps: List[Dict[str, Any]], warnings: List[str],
                    data: Optional[Dict[str, Any]] = None,
                    verification: Optional[Dict[str, Any]] = None) -> Path:
    files = []
    for name in (STUDENT_JSON, AUDIO_WAV, SUBTITLE_SRT, VIDEO_MP4, MANIFEST_JSON):
        p = out_dir / name
        if p.exists():
            files.append({"path": str(p.relative_to(ROOT)), "bytes": p.stat().st_size,
                          "sha256": _sha256(p)})
    manifest = {
        "schema_version": "1.0",
        "generated_at": _now(),
        "generator": {
            "name": "askback-ai-student",
            "stage": "AI 學生迷思、動畫、TTS 與影片合成",
            "excluded_scope": [
                "AI 教學設計師",
                "教師端迷思診斷報告",
                "instructional_design.json",
                "正確答案生成與教師講解",
            ],
        },
        "steps": steps,
        "files": files,
        "environment": {
            "python": sys.version.split()[0],
            "platform": platform.platform(),
            "ffmpeg": _ffmpeg_version(),
            "tts_providers": available_providers(),
        },
        "verification": verification,
        "warnings": warnings,
        "notes": [
            "本 manifest 只記錄生成流程與驗證資訊，不含任何 API 金鑰。",
            "本 manifest 不取代 student_question.json。",
            "輸出為 AI 生成學生示範，動畫與語音僅呈現學生的迷思、困惑與提問。",
        ],
    }
    path = out_dir / MANIFEST_JSON
    with open(path, "w", encoding="utf-8") as fh:
        json.dump(manifest, fh, ensure_ascii=False, indent=2)
        fh.write("\n")
    return path


# ---------------------------------------------------------------------------
def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description="AskBack AI Student")
    p.add_argument("command", choices=["units", "student", "tts", "srt", "animate", "all", "verify"],
                   nargs="?", default="all")
    p.add_argument("--unit", default=None, help="學習單元 ID（用 python main.py units 查看）")
    p.add_argument("--mc", type=int, default=0, help="該單元的第幾個卡關點")
    p.add_argument("--mode", choices=["auto", "template", "llm"], default="auto",
                   help="提問生成模式（auto=有金鑰用 LLM，否則內建資料庫）")
    p.add_argument("--turns", type=int, default=1, help="互動輪數（1=只有學生提問）")
    p.add_argument("--provider", default=None, help="TTS 供應商: auto/edge/openai/azure/sapi")
    p.add_argument("--student", default=None, help="student_question.json 路徑")
    p.add_argument("--video", default=None, help="要驗證的影片路徑")
    p.add_argument("--out", default=str(DEFAULT_OUT), help="輸出目錄")
    return p


def main(argv: Optional[List[str]] = None) -> int:
    args = build_parser().parse_args(argv)
    if args.provider is None:
        args.provider = os.environ.get("ASKBACK_TTS_PROVIDER", "auto")
    if args.command == "units":
        return cmd_units(args)
    if args.command == "student":
        cmd_student(args)
        return 0
    if args.command == "tts":
        cmd_tts(args)
        return 0
    if args.command == "verify":
        res = cmd_verify(args)
        return 0 if res.get("ok") else 1
    if args.command in ("srt", "animate"):
        # 需要完整時間軸，直接走 all 的前段
        args.turns = max(1, args.turns)
        return cmd_all(args)
    return cmd_all(args)


if __name__ == "__main__":
    raise SystemExit(main())

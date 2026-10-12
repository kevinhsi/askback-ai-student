"""影片驗證：解碼、串流、音量、動態畫面與長度檢查。"""

from __future__ import annotations

import json
import shutil
import subprocess
import tempfile
from pathlib import Path
from typing import Any, Dict, List, Optional

import numpy as np
from PIL import Image

FFPROBE = shutil.which("ffprobe") or "ffprobe"
FFMPEG = shutil.which("ffmpeg") or "ffmpeg"


class VerifyError(RuntimeError):
    """影片驗證失敗。"""


def _run(args: List[str], timeout: float = 300.0) -> subprocess.CompletedProcess:
    try:
        return subprocess.run(args, stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=timeout)
    except FileNotFoundError as exc:
        raise VerifyError(f"找不到工具: {args[0]}") from exc


def probe(path: Path | str) -> Dict[str, Any]:
    """以 ffprobe 取得串流資訊（解碼檢查）。"""
    path = Path(path)
    if not path.exists():
        raise VerifyError(f"檔案不存在: {path}")
    proc = _run([
        FFPROBE, "-v", "error", "-print_format", "json",
        "-show_format", "-show_streams", str(path),
    ])
    if proc.returncode != 0:
        raise VerifyError("ffprobe 解碼失敗: " + proc.stderr.decode("utf-8", "replace")[-400:])
    try:
        data = json.loads(proc.stdout.decode("utf-8"))
    except ValueError as exc:
        raise VerifyError("ffprobe 回傳非 JSON") from exc
    return data


def decode_check(path: Path | str) -> tuple[bool, str]:
    """完整解碼一次，回傳 (是否成功, 錯誤訊息)。"""
    proc = _run([FFMPEG, "-v", "error", "-xerror", "-i", str(path), "-f", "null", "-"])
    err = proc.stderr.decode("utf-8", "replace").strip()
    return proc.returncode == 0 and not err, err[-600:]


def audio_stats(path: Path | str) -> Dict[str, float]:
    """音量統計（volumedetect）。"""
    proc = _run([FFMPEG, "-hide_banner", "-i", str(path), "-af", "volumedetect", "-f", "null", "-"])
    text = proc.stderr.decode("utf-8", "replace")
    stats: Dict[str, float] = {}
    for line in text.splitlines():
        for key in ("mean_volume", "max_volume"):
            if key in line and ":" in line:
                try:
                    stats[key] = float(line.rsplit(":", 1)[1].strip().split()[0])
                except (ValueError, IndexError):
                    pass
    return stats


def motion_check(path: Path | str, samples: int = 6, threshold: float = 1.5) -> Dict[str, Any]:
    """抽樣比對相鄰畫面，確認影片真的有動態畫面（不是靜態圖）。"""
    path = Path(path)
    with tempfile.TemporaryDirectory(prefix="askback_motion_") as td:
        pattern = str(Path(td) / "f_%02d.png")
        proc = _run([
            FFMPEG, "-v", "error", "-i", str(path),
            "-vf", "fps=2", "-frames:v", str(samples), "-y", pattern,
        ])
        if proc.returncode != 0:
            return {"ok": False, "reason": "無法抽幀: " + proc.stderr.decode("utf-8", "replace")[-300:]}
        files = sorted(Path(td).glob("f_*.png"))
        if len(files) < 2:
            return {"ok": False, "reason": f"抽幀不足（{len(files)}）"}
        diffs: List[float] = []
        prev: Optional[np.ndarray] = None
        for f in files:
            arr = np.asarray(Image.open(f).convert("L"), dtype=np.float32)
            if prev is not None:
                diffs.append(float(np.mean(np.abs(arr - prev))))
            prev = arr
        max_diff = max(diffs) if diffs else 0.0
        moving = max_diff >= threshold
        return {
            "ok": moving,
            "frames_sampled": len(files),
            "mean_diffs": [round(x, 3) for x in diffs],
            "max_diff": round(max_diff, 3),
            "threshold": threshold,
            "reason": "ok" if moving else f"畫面差異過小（{max_diff:.3f} < {threshold}），疑似靜態圖",
        }


def verify_video(
    path: Path | str,
    *,
    target_min: float = 30.0,
    target_max: float = 90.0,
    min_volume_db: float = -45.0,
    check_motion: bool = True,
) -> Dict[str, Any]:
    """完整驗證最終 MP4：可解碼、有畫面、有音軌、音量、長度、動態畫面。"""
    path = Path(path)
    result: Dict[str, Any] = {"path": str(path), "checks": {}, "ok": False}
    checks: Dict[str, Any] = result["checks"]

    try:
        info = probe(path)
    except VerifyError as exc:
        result["error"] = str(exc)
        return result

    streams = info.get("streams", [])
    video = [s for s in streams if s.get("codec_type") == "video"]
    audio = [s for s in streams if s.get("codec_type") == "audio"]
    fmt = info.get("format", {})
    duration = float(fmt.get("duration") or 0.0)

    checks["has_video_stream"] = bool(video)
    checks["has_audio_stream"] = bool(audio)
    checks["duration_seconds"] = round(duration, 3)
    checks["duration_in_range"] = target_min <= duration <= target_max
    checks["file_size_bytes"] = path.stat().st_size

    if video:
        v = video[0]
        checks["width"] = int(v.get("width") or 0)
        checks["height"] = int(v.get("height") or 0)
        checks["video_codec"] = v.get("codec_name")
        fps_val = 0.0
        rate = v.get("avg_frame_rate") or v.get("r_frame_rate") or "0/1"
        try:
            num, den = rate.split("/")
            fps_val = float(num) / float(den) if float(den) else 0.0
        except (ValueError, ZeroDivisionError):
            fps_val = 0.0
        checks["fps"] = round(fps_val, 2)
        checks["frame_count"] = int(v.get("nb_frames") or 0)

    ok_dec, dec_err = decode_check(path)
    checks["decodable"] = ok_dec
    if dec_err:
        checks["decode_errors"] = dec_err

    if audio:
        stats = audio_stats(path)
        checks["audio"] = stats
        max_vol = stats.get("max_volume", -120.0)
        checks["audio_not_silent"] = max_vol > min_volume_db
        checks["audio_max_volume_db"] = max_vol
        a = audio[0]
        checks["audio_codec"] = a.get("codec_name")
        checks["audio_sample_rate"] = int(a.get("sample_rate") or 0)

    if check_motion:
        checks["motion"] = motion_check(path)

    required = [
        checks.get("has_video_stream"),
        checks.get("has_audio_stream"),
        checks.get("duration_in_range"),
        checks.get("decodable"),
        checks.get("audio_not_silent", False),
    ]
    if check_motion:
        required.append(bool(checks.get("motion", {}).get("ok")))
    result["ok"] = all(required)
    return result

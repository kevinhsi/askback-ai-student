"""音畫合成：組裝語音、呼叫動畫渲染器並輸出 MP4。"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence

import numpy as np

from tts_generator import audio as A


def assemble_audio(
    cue_paths: Sequence[Path | str],
    timeline: Dict[str, Any],
    out_path: Path | str,
) -> Dict[str, Any]:
    """依時間軸把逐句語音 + 停頓組成完整旁白軌（student_voice.wav）。"""
    plan_segs: List[np.ndarray] = []
    for cue in timeline["cues"]:
        idx = cue["index"]
        pcm = A.read_pcm(Path(cue_paths[idx]))
        if pcm.size == 0:
            raise A.AudioToolError(f"第 {idx} 句語音為空白，拒絕合成")
        plan_segs.append(A.silence(cue["pre_silence"]))
        plan_segs.append(pcm)
        plan_segs.append(A.silence(cue["post_silence"]))
    merged = np.concatenate(plan_segs) if plan_segs else np.zeros(0, dtype=np.int16)
    A.write_wav(out_path, merged)
    info = {
        "path": str(out_path),
        "duration": round(merged.size / float(A.DEFAULT_SR), 3),
        "samples": int(merged.size),
        "peak": A.peak(merged),
        "rms": round(A.rms(merged), 2),
    }
    if info["duration"] < 0.3 or info["peak"] < 400:
        raise A.AudioToolError(f"組裝後的旁白疑似空白: {info}")
    return info


def render_and_mux(
    script: Dict[str, Any],
    audio_path: Path | str,
    out_path: Path | str,
    *,
    fps: Optional[int] = None,
    log: Optional[List[str]] = None,
) -> Dict[str, Any]:
    """以語音包絡驅動嘴型，渲染動畫並與語音合成 MP4。"""
    from animation_generator.renderer import render_animation  # 延遲匯入避免循環相依

    pcm = A.read_pcm(Path(audio_path))
    n_frames = int(np.ceil(float(script["duration"]) * int(script["fps"])))
    env = A.envelope(pcm, int(script["fps"]), n_frames)
    result = render_animation(script, audio_path, out_path, mouth_env=env, log=log)
    result["audio"] = str(audio_path)
    return result

"""音訊工具：標準化、讀寫 PCM、拼接、長度與包絡分析。

所有音訊統一轉成 24 kHz / mono / 16-bit PCM，方便精確對齊影片時間軸。
外部工具一律使用 ffmpeg（本專案已列為必要相依）。
"""

from __future__ import annotations

import shutil
import subprocess
from pathlib import Path
from typing import Iterable, List, Sequence, Tuple

import numpy as np

DEFAULT_SR = 24000

FFMPEG = shutil.which("ffmpeg") or "ffmpeg"
FFPROBE = shutil.which("ffprobe") or "ffprobe"


class AudioToolError(RuntimeError):
    """音訊處理工具失敗。"""


def _run(args: Sequence[str], *, timeout: float = 120.0) -> subprocess.CompletedProcess:
    try:
        proc = subprocess.run(
            list(args),
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            timeout=timeout,
        )
    except FileNotFoundError as exc:
        raise AudioToolError(f"找不到外部工具: {args[0]}（請確認 ffmpeg 已安裝）") from exc
    except subprocess.TimeoutExpired as exc:
        raise AudioToolError(f"工具逾時: {args[0]}") from exc
    if proc.returncode != 0:
        tail = proc.stderr.decode("utf-8", "replace").strip().splitlines()[-3:]
        raise AudioToolError(f"{args[0]} 失敗: {' | '.join(tail)}")
    return proc


def standardize(src: Path | str, dst: Path | str, sr: int = DEFAULT_SR) -> Path:
    """把任何 ffmpeg 可讀的音訊轉成 16-bit PCM mono WAV。"""
    src, dst = Path(src), Path(dst)
    dst.parent.mkdir(parents=True, exist_ok=True)
    _run([FFMPEG, "-y", "-v", "error", "-i", str(src), "-ar", str(sr), "-ac", "1",
          "-c:a", "pcm_s16le", str(dst)])
    if not dst.exists() or dst.stat().st_size < 44:
        raise AudioToolError(f"音訊標準化後檔案为空: {dst}")
    return dst


def read_pcm(path: Path | str, sr: int = DEFAULT_SR) -> np.ndarray:
    """以 ffmpeg 讀成 mono int16 PCM 陣列。"""
    proc = _run(
        [FFMPEG, "-v", "error", "-i", str(path), "-f", "s16le", "-acodec", "pcm_s16le",
         "-ac", "1", "-ar", str(sr), "-"]
    )
    return np.frombuffer(proc.stdout, dtype=np.int16)


def write_wav(path: Path | str, pcm: np.ndarray, sr: int = DEFAULT_SR) -> Path:
    """以 ffmpeg 寫 WAV（避免 stdlib wave 對齊問題）。"""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    pcm = np.asarray(pcm, dtype=np.int16)
    try:
        proc = subprocess.run(
            [FFMPEG, "-y", "-v", "error", "-f", "s16le", "-ar", str(sr), "-ac", "1",
             "-i", "pipe:0", str(path)],
            input=pcm.tobytes(),
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            timeout=120,
        )
    except FileNotFoundError as exc:
        raise AudioToolError("找不到 ffmpeg") from exc
    if proc.returncode != 0:
        raise AudioToolError("寫 WAV 失敗: " + proc.stderr.decode("utf-8", "replace")[-300:])
    return path


def duration(path: Path | str, sr: int = DEFAULT_SR) -> float:
    """回傳音訊長度（秒）。"""
    return len(read_pcm(path, sr)) / float(sr)


def rms(pcm: np.ndarray) -> float:
    if pcm.size == 0:
        return 0.0
    return float(np.sqrt(np.mean(np.square(pcm.astype(np.float64)))))


def peak(pcm: np.ndarray) -> int:
    if pcm.size == 0:
        return 0
    return int(np.max(np.abs(pcm)))


def silence(seconds: float, sr: int = DEFAULT_SR) -> np.ndarray:
    return np.zeros(int(round(seconds * sr)), dtype=np.int16)


def concat_pcm(
    parts: Iterable[np.ndarray],
    gaps: Sequence[float] = (),
    sr: int = DEFAULT_SR,
) -> np.ndarray:
    """依序拼接音訊片段，並在片段間插入靜音（gap 秒）。

    ``gaps`` 的長度為 ``len(parts) - 1`` 或 ``len(parts)``（最後一項忽略）。
    """
    pieces: List[np.ndarray] = [np.asarray(p, dtype=np.int16) for p in parts]
    gap_list = list(gaps) + [0.0] * max(0, len(pieces) - len(gaps) - 1)
    out: List[np.ndarray] = []
    for i, piece in enumerate(pieces):
        out.append(piece)
        if i < len(pieces) - 1:
            out.append(silence(gap_list[i], sr))
    if not out:
        return np.zeros(0, dtype=np.int16)
    return np.concatenate(out)


def envelope(pcm: np.ndarray, fps: int, n_frames: int, sr: int = DEFAULT_SR) -> np.ndarray:
    """逐影格的音量包絡（0..1），用來驅動嘴巴開合。"""
    pcm = pcm.astype(np.float64)
    env = np.zeros(n_frames, dtype=np.float64)
    win = max(1, sr // fps)
    for i in range(n_frames):
        start = i * win
        chunk = pcm[start:start + win]
        if chunk.size:
            env[i] = np.sqrt(np.mean(np.square(chunk)))
    ref = np.percentile(env, 97) if env.size and np.max(env) > 0 else 0.0
    if ref <= 0:
        return np.zeros(n_frames, dtype=np.float64)
    env = np.clip(env / ref, 0.0, 1.0)
    # 平滑，避免嘴巴抖動過快
    kernel = np.array([0.25, 0.5, 0.25])
    env = np.convolve(env, kernel, mode="same")
    return np.clip(env, 0.0, 1.0)


def check_non_blank(pcm: np.ndarray, sr: int = DEFAULT_SR, min_seconds: float = 0.2,
                    min_peak: int = 400) -> Tuple[bool, str]:
    """檢查音訊不是空白（長度與音量都要夠）。"""
    if pcm.size == 0:
        return False, "音訊樣本數為 0"
    sec = pcm.size / sr
    if sec < min_seconds:
        return False, f"音訊長度過短: {sec:.3f}s < {min_seconds}s"
    if peak(pcm) < min_peak:
        return False, f"音量過低（peak={peak(pcm)} < {min_peak}），疑似空白音訊"
    return True, f"ok duration={sec:.3f}s peak={peak(pcm)} rms={rms(pcm):.1f}"

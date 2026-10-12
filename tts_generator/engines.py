"""TTS 供應商實作與供應鏈（provider chain）。

設計原則：
1. 金鑰只從環境變數讀取，不寫入任何輸出檔案。
2. 每個引擎獨立回報明確錯誤（缺金鑰、語音不支援、空白音訊、服務失敗）。
3. ``synthesize()`` 依序嘗試供應商，全部失敗時抛出 :class:`TTSError`
   並附上每個供應商的失敗原因（不含金鑰）。
4. 保證輸出為「非空白、可解碼」的 16-bit PCM WAV；絕不回傳空白音訊冒充成功。
"""

from __future__ import annotations

import asyncio
import base64
import json
import os
import platform
import shutil
import subprocess
import tempfile
import urllib.error
import urllib.request
import uuid
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence

from . import audio as A

DEFAULT_VOICE_EDGE = "zh-TW-XiaoXiaoNeural"
PROVIDER_ORDER = ("openai", "azure", "edge", "sapi")


class TTSError(RuntimeError):
    """TTS 產生失敗（包含服務失敗與空白音訊）。"""


class MissingKeyError(TTSError):
    """缺少 API 金鑰。"""


class UnsupportedVoiceError(TTSError):
    """語音設定不支援或語音不存在。"""


class EmptyAudioError(TTSError):
    """引擎回傳空白／極短音訊。"""


def _env(name: str) -> str:
    return os.environ.get(name, "").strip()


def _default_rate() -> str:
    return _env("ASKBACK_TTS_RATE") or "2"


# ---------------------------------------------------------------------------
# 工具
# ---------------------------------------------------------------------------
def _standardize_to_wav(src: Path, dst: Path) -> Path:
    return A.standardize(src, dst)


def _guard_non_blank(path: Path) -> None:
    pcm = A.read_pcm(path)
    ok, reason = A.check_non_blank(pcm)
    if not ok:
        raise EmptyAudioError(f"TTS 產生空白或過短音訊: {reason}")


def _ps_encode(script: str) -> str:
    return base64.b64encode(script.encode("utf-16-le")).decode("ascii")


def _ps_quote(value: str) -> str:
    return "'" + value.replace("'", "''") + "'"


def _run_powershell(script: str, timeout: float = 120.0) -> subprocess.CompletedProcess:
    exe = shutil.which("powershell") or shutil.which("pwsh")
    if not exe:
        raise TTSError("找不到 PowerShell，無法使用本機 SAPI 語音引擎")
    return subprocess.run(
        [exe, "-NoProfile", "-NonInteractive", "-EncodedCommand", _ps_encode(script)],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        timeout=timeout,
    )


# ---------------------------------------------------------------------------
# 各供應商
# ---------------------------------------------------------------------------
def sapi_voices() -> List[Dict[str, str]]:
    """列出本機 Windows System.Speech 已安裝語音。"""
    script = (
        "[Console]::OutputEncoding=[System.Text.Encoding]::UTF8\n"
        "Add-Type -AssemblyName System.Speech\n"
        "$s=New-Object System.Speech.Synthesis.SpeechSynthesizer\n"
        "foreach($v in $s.GetInstalledVoices()){\n"
        "  $i=$v.VoiceInfo\n"
        "  Write-Output ($i.Name+'|'+$i.Culture+'|'+$i.Gender)\n"
        "}\n"
        "$s.Dispose()\n"
    )
    proc = _run_powershell(script, timeout=60.0)
    if proc.returncode != 0:
        raise TTSError("列出本機語音失敗: " + proc.stderr.decode("utf-8", "replace")[-200:])
    text = proc.stdout.decode("utf-8", "replace")
    voices: List[Dict[str, str]] = []
    for line in text.splitlines():
        line = line.strip()
        if not line or "|" not in line:
            continue
        name, culture, gender = (line.split("|") + ["", ""])[:3]
        voices.append({"name": name.strip(), "culture": culture.strip(), "gender": gender.strip()})
    return voices


def _pick_sapi_voice(requested: str = "") -> str:
    voices = sapi_voices()
    if not voices:
        raise UnsupportedVoiceError("本機沒有任何可用的 System.Speech 語音")
    if requested:
        for v in voices:
            if v["name"].lower() == requested.lower():
                return v["name"]
        raise UnsupportedVoiceError(f"找不到指定的本機語音: {requested}")
    zh = [v for v in voices if v["culture"].lower().startswith("zh-tw")]
    if not zh:
        raise UnsupportedVoiceError(
            "本機未安裝繁體中文（zh-TW）語音，無法產生台灣華語語音"
        )
    return zh[0]["name"]


def _sapi_speak(text: str, out_wav: Path, *, voice: str = "", rate: Optional[int] = None) -> Path:
    """本機 Windows TTS（System.Speech），不需任何 API 金鑰。"""
    if platform.system() != "Windows":
        raise UnsupportedVoiceError("SAPI 語音引擎僅適用於 Windows")
    voice_name = _pick_sapi_voice(voice)
    try:
        rate_i = int(rate if rate is not None else _default_rate())
    except ValueError:
        rate_i = 2
    rate_i = max(-10, min(10, rate_i))
    out_wav = Path(out_wav)

    def _script(payload: str, ssml: bool) -> str:
        method = "SpeakSsml" if ssml else "Speak"
        return (
            "[Console]::OutputEncoding=[System.Text.Encoding]::UTF8\n"
            "Add-Type -AssemblyName System.Speech\n"
            "$s=New-Object System.Speech.Synthesis.SpeechSynthesizer\n"
            f"try{{$s.SelectVoice({_ps_quote(voice_name)})}}catch{{Write-Error 'VOICE_NOT_FOUND'; exit 4}}\n"
            f"$s.Rate={rate_i}\n"
            f"$s.SetOutputToWaveFile({_ps_quote(str(out_wav))})\n"
            f"try{{$s.{method}({payload})}}catch{{Write-Error $_.Exception.Message; exit 5}}\n"
            "$s.Dispose()\n"
            "exit 0\n"
        )

    escaped = text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
    ssml = (
        '<speak version="1.0" xmlns="http://www.w3.org/2001/10/synthesis" xml:lang="zh-TW">'
        '<prosody pitch="+12%">' + escaped + "</prosody></speak>"
    )
    # 先嘗試 SSML 微調音高（較像小學生），失敗則退回一般朗讀
    proc = _run_powershell(_script(_ps_quote(ssml), True))
    if proc.returncode != 0 or not out_wav.exists() or out_wav.stat().st_size <= 44:
        if out_wav.exists():
            out_wav.unlink(missing_ok=True)
        proc = _run_powershell(_script(_ps_quote(text), False))
    if proc.returncode != 0 or not out_wav.exists() or out_wav.stat().st_size <= 44:
        err = proc.stderr.decode("utf-8", "replace").strip().splitlines()
        tail = err[-1] if err else "unknown"
        if "VOICE_NOT_FOUND" in tail:
            raise UnsupportedVoiceError(f"本機語音不存在: {voice_name}")
        raise TTSError(f"SAPI 合成失敗: {tail[:200]}")
    return out_wav


def _edge_speak(text: str, out_wav: Path, *, voice: str = "", rate: Optional[int] = None) -> Path:
    try:
        import edge_tts  # noqa: PLC0415
    except ImportError as exc:  # pragma: no cover
        raise MissingKeyError("edge-tts 未安裝（pip install edge-tts）") from exc

    voice_name = voice or _env("ASKBACK_TTS_VOICE") or DEFAULT_VOICE_EDGE
    if not voice_name.startswith("zh-TW"):
        raise UnsupportedVoiceError(f"edge-tts 語音非台灣繁體中文: {voice_name}")
    rate_val = int(rate if rate is not None else _default_rate())
    rate_str = f"{'+' if rate_val >= 0 else ''}{rate_val}%"

    async def _run(target: Path) -> None:
        comm = edge_tts.Communicate(text, voice_name, rate=rate_str)
        with open(target, "wb") as fh:
            async for chunk in comm.stream():
                if chunk.get("type") == "audio":
                    fh.write(chunk["data"])

    tmp_mp3 = out_wav.with_suffix(".edge.mp3")
    try:
        asyncio.run(_run(tmp_mp3))
    except Exception as exc:  # noqa: BLE001 - edge-tts 例外型別眾多
        tmp_mp3.unlink(missing_ok=True)
        raise TTSError(f"edge-tts 服務失敗: {type(exc).__name__}") from exc
    if not tmp_mp3.exists() or tmp_mp3.stat().st_size <= 128:
        tmp_mp3.unlink(missing_ok=True)
        raise EmptyAudioError("edge-tts 未回傳音訊")
    _standardize_to_wav(tmp_mp3, out_wav)
    tmp_mp3.unlink(missing_ok=True)
    return out_wav


def _openai_speak(text: str, out_wav: Path, *, voice: str = "", rate: Optional[int] = None) -> Path:
    key = _env("OPENAI_API_KEY")
    if not key:
        raise MissingKeyError("缺少 OPENAI_API_KEY（OpenAI TTS 需要金鑰）")
    base = _env("OPENAI_BASE_URL").rstrip("/") or "https://api.openai.com/v1"
    model = _env("ASKBACK_TTS_OPENAI_MODEL") or "tts-1"
    use_voice = voice or _env("ASKBACK_TTS_OPENAI_VOICE") or "shimmer"
    payload = {
        "model": model,
        "voice": use_voice,
        "input": text,
        "response_format": "wav",
        "speed": 1.0,
    }
    req = urllib.request.Request(
        f"{base}/audio/speech",
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json", "Authorization": f"Bearer {key}"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=90) as resp:
            blob = resp.read()
    except urllib.error.HTTPError as exc:
        if exc.code in (401, 403):
            raise MissingKeyError("OpenAI TTS 金鑰無效或權限不足") from exc
        raise TTSError(f"OpenAI TTS HTTP {exc.code}") from exc
    except (urllib.error.URLError, OSError) as exc:
        raise TTSError(f"OpenAI TTS 連線失敗: {type(exc).__name__}") from exc
    if not blob:
        raise EmptyAudioError("OpenAI TTS 回傳空白音訊")
    raw = out_wav.with_suffix(".openai.raw")
    raw.write_bytes(blob)
    try:
        _standardize_to_wav(raw, out_wav)
    finally:
        raw.unlink(missing_ok=True)
    return out_wav


def _azure_speak(text: str, out_wav: Path, *, voice: str = "", rate: Optional[int] = None) -> Path:
    key = _env("AZURE_SPEECH_KEY")
    region = _env("AZURE_SPEECH_REGION") or "eastasia"
    if not key:
        raise MissingKeyError("缺少 AZURE_SPEECH_KEY（Azure Speech 需要金鑰）")
    use_voice = voice or _env("ASKBACK_TTS_AZURE_VOICE") or "zh-TW-HsiaoChenNeural"
    if not use_voice.lower().startswith("zh-tw"):
        raise UnsupportedVoiceError(f"Azure 語音非台灣繁體中文: {use_voice}")

    token_url = f"https://{region}.api.cognitive.microsoft.com/sts/v1.0/issueToken"
    token_req = urllib.request.Request(
        token_url,
        data=b"",
        headers={"Ocp-Apim-Subscription-Key": key, "Content-Type": "application/x-www-form-urlencoded"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(token_req, timeout=60) as resp:
            token = resp.read().decode("utf-8")
    except (urllib.error.HTTPError, urllib.error.URLError, OSError) as exc:
        raise MissingKeyError("Azure Speech 金鑰驗證失敗") from exc

    escaped = text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
    ssml = (
        '<speak version="1.0" xmlns="http://www.w3.org/2001/10/synthesis" xml:lang="zh-TW">'
        f'<voice name="{use_voice}"><prosody rate="+8%" pitch="+10%">{escaped}</prosody></voice></speak>'
    )
    tts_req = urllib.request.Request(
        f"https://{region}.tts.speech.microsoft.com/cognitiveservices/v1",
        data=ssml.encode("utf-8"),
        headers={
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/ssml+xml",
            "X-Microsoft-OutputFormat": "riff-24khz-16bit-mono-pcm",
            "User-Agent": "askback-ai-student",
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(tts_req, timeout=90) as resp:
            blob = resp.read()
    except urllib.error.HTTPError as exc:
        raise TTSError(f"Azure TTS HTTP {exc.code}") from exc
    except (urllib.error.URLError, OSError) as exc:
        raise TTSError(f"Azure TTS 連線失敗: {type(exc).__name__}") from exc
    if not blob:
        raise EmptyAudioError("Azure TTS 回傳空白音訊")
    raw = out_wav.with_suffix(".azure.raw")
    raw.write_bytes(blob)
    try:
        _standardize_to_wav(raw, out_wav)
    finally:
        raw.unlink(missing_ok=True)
    return out_wav


ENGINES = {
    "sapi": _sapi_speak,
    "edge": _edge_speak,
    "openai": _openai_speak,
    "azure": _azure_speak,
}


# ---------------------------------------------------------------------------
# 供應商狀態與合成
# ---------------------------------------------------------------------------
def available_providers() -> List[Dict[str, Any]]:
    """回報每個供應商是否可用（只檢查設定，不發出請求）。"""
    out: List[Dict[str, Any]] = []
    if _env("OPENAI_API_KEY"):
        out.append({"provider": "openai", "available": True, "reason": "OPENAI_API_KEY 已設定"})
    else:
        out.append({"provider": "openai", "available": False, "reason": "缺少 OPENAI_API_KEY"})
    if _env("AZURE_SPEECH_KEY"):
        out.append({"provider": "azure", "available": True, "reason": "AZURE_SPEECH_KEY 已設定"})
    else:
        out.append({"provider": "azure", "available": False, "reason": "缺少 AZURE_SPEECH_KEY"})
    edge_ok = True
    edge_reason = "免費神經語音（需網路）"
    if shutil.which("ffmpeg") is None:
        edge_ok, edge_reason = False, "缺少 ffmpeg"
    out.append({"provider": "edge", "available": edge_ok, "reason": edge_reason})
    if platform.system() == "Windows":
        try:
            name = _pick_sapi_voice(_env("ASKBACK_TTS_SAPI_VOICE"))
            out.append({"provider": "sapi", "available": True, "reason": f"本機語音 {name}"})
        except TTSError as exc:
            out.append({"provider": "sapi", "available": False, "reason": str(exc)})
    else:
        out.append({"provider": "sapi", "available": False, "reason": "非 Windows 平台"})
    return out


def _resolve_chain(provider: str) -> List[str]:
    provider = (provider or "auto").lower()
    if provider not in ("auto", "") and provider not in ENGINES:
        raise UnsupportedVoiceError(f"不支援的 TTS 供應商: {provider}")
    if provider in ("auto", ""):
        base = [p for p in PROVIDER_ORDER]
    else:
        base = [provider] + [p for p in PROVIDER_ORDER if p != provider]
    # 已設定金鑰的雲端供應商優先，其餘照序
    configured = []
    rest = []
    for p in base:
        (configured if p in ("openai", "azure") and _env(
            "OPENAI_API_KEY" if p == "openai" else "AZURE_SPEECH_KEY") else rest).append(p)
    return configured + rest


def synthesize(
    text: str,
    out_path: Path | str,
    *,
    provider: str = "auto",
    voice: str = "",
    rate: Optional[int] = None,
    allow_fallback: bool = True,
) -> Dict[str, Any]:
    """把一段繁體中文文字轉成標準化的 WAV，回傳引擎資訊與嘗試紀錄。"""
    if not text or not text.strip():
        raise TTSError("文字內容為空白，拒絕產生音訊")
    out_path = Path(out_path)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    chain = _resolve_chain(provider)
    if not allow_fallback and provider not in ("auto", ""):
        chain = [provider]

    attempts: List[Dict[str, Any]] = []
    for name in chain:
        engine = ENGINES[name]
        tmp = out_path.with_suffix(f".{name}{out_path.suffix}")
        try:
            engine(text, tmp, voice=voice, rate=rate)
            _standardize_to_wav(tmp, out_path)
            tmp.unlink(missing_ok=True)
            _guard_non_blank(out_path)
        except A.AudioToolError as exc:
            attempts.append({"provider": name, "status": "error", "error": f"工具失敗: {exc}"})
            tmp.unlink(missing_ok=True)
            continue
        except TTSError as exc:
            attempts.append({"provider": name, "status": "error", "error": f"{type(exc).__name__}: {exc}"})
            tmp.unlink(missing_ok=True)
            continue
        except Exception as exc:  # noqa: BLE001 - 不可預期的引擎例外一律轉成失敗紀錄
            attempts.append({"provider": name, "status": "error", "error": f"未預期錯誤: {type(exc).__name__}"})
            tmp.unlink(missing_ok=True)
            continue

        pcm = A.read_pcm(out_path)
        return {
            "provider": name,
            "voice": voice or _env("ASKBACK_TTS_VOICE") or (
                _env("ASKBACK_TTS_SAPI_VOICE") or "本機 zh-TW 語音"
            ),
            "path": str(out_path),
            "duration": round(len(pcm) / float(A.DEFAULT_SR), 3),
            "attempts": attempts,
        }

    summary = "; ".join(f"{a['provider']}={a['error']}" for a in attempts) or "沒有任何可用供應商"
    raise TTSError(f"所有 TTS 供應商皆失敗: {summary}")


def synthesize_lines(
    lines: Sequence[str],
    workdir: Path | str,
    *,
    provider: str = "auto",
    prefix: str = "cue",
) -> Dict[str, Any]:
    """逐句合成（每句一個 WAV），回傳逐句時長，供時間軸精準對齊。"""
    workdir = Path(workdir)
    workdir.mkdir(parents=True, exist_ok=True)
    records: List[Dict[str, Any]] = []
    engine_used: Optional[str] = None
    all_attempts: List[Dict[str, Any]] = []
    for i, line in enumerate(lines):
        target = workdir / f"{prefix}_{i:02d}.wav"
        result = synthesize(line, target, provider=provider)
        if engine_used is None:
            engine_used = result["provider"]
        for att in result["attempts"]:
            if att not in all_attempts:
                all_attempts.append(att)
        records.append({"index": i, "text": line, "path": str(target), "duration": result["duration"]})
    return {
        "provider": engine_used,
        "cues": records,
        "total_duration": round(sum(r["duration"] for r in records), 3),
        "attempts": all_attempts,
    }

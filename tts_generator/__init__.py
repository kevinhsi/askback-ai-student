"""繁體中文（台灣華語）TTS 語音生成模組。

- 供應商可透過環境變數 ``ASKBACK_TTS_PROVIDER`` 切換（auto/edge/openai/azure/sapi）
- 金鑰一律只從環境變數讀取
- 自動處理：服務失敗、空白音訊、不支援的語音設定
- 無任何雲端金鑰時，退回本機 Windows SAPI zh-TW 語音引擎
"""

from .audio import (
    DEFAULT_SR,
    concat_pcm,
    duration,
    envelope,
    read_pcm,
    standardize,
    write_wav,
)
from .engines import (
    EmptyAudioError,
    MissingKeyError,
    TTSError,
    UnsupportedVoiceError,
    available_providers,
    synthesize,
    synthesize_lines,
)

__all__ = [
    "DEFAULT_SR",
    "EmptyAudioError",
    "MissingKeyError",
    "TTSError",
    "UnsupportedVoiceError",
    "available_providers",
    "concat_pcm",
    "duration",
    "envelope",
    "read_pcm",
    "standardize",
    "synthesize",
    "synthesize_lines",
    "write_wav",
]

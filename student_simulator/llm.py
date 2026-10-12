"""可選的 LLM 文本生成層。

只有在環境變數明確設定 ``ASKBACK_LLM_PROVIDER=openai`` 且提供金鑰時才會使用；
否則自動退回內建迷思資料庫（模板模式），保證離線也能產出合法的
``student_question.json``。

任何金鑰只從環境變數讀取，不會寫入輸出檔案、日誌或例外訊息。
"""

from __future__ import annotations

import json
import os
import urllib.error
import urllib.request
from typing import Optional


class LLMError(RuntimeError):
    """LLM 呼叫失敗（網路、金鑰、回應格式）。"""


def _env(name: str) -> str:
    return os.environ.get(name, "").strip()


def llm_configured() -> bool:
    provider = _env("ASKBACK_LLM_PROVIDER").lower()
    if provider in ("", "none", "template"):
        return False
    if provider == "openai":
        return bool(_env("OPENAI_API_KEY"))
    return False


def complete(system: str, user: str, *, timeout: float = 60.0) -> str:
    """回傳 LLM 文字回應；未設定或失敗時抛出 :class:`LLMError`。"""
    provider = _env("ASKBACK_LLM_PROVIDER").lower()
    if provider in ("", "none", "template"):
        raise LLMError("ASKBACK_LLM_PROVIDER 未啟用 LLM（模板模式）")
    if provider != "openai":
        raise LLMError(f"不支援的 LLM 供應商: {provider}")

    key = _env("OPENAI_API_KEY")
    if not key:
        raise LLMError("缺少 OPENAI_API_KEY，無法使用 LLM")

    base = _env("OPENAI_BASE_URL").rstrip("/") or "https://api.openai.com/v1"
    model = _env("ASKBACK_LLM_MODEL") or "gpt-4o-mini"
    payload = {
        "model": model,
        "messages": [
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ],
        "temperature": 0.8,
    }
    req = urllib.request.Request(
        f"{base}/chat/completions",
        data=json.dumps(payload).encode("utf-8"),
        headers={
            "Content-Type": "application/json",
            "Authorization": f"Bearer {key}",
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            data = json.loads(resp.read().decode("utf-8"))
    except (urllib.error.URLError, OSError, ValueError) as exc:  # noqa: BLE001
        raise LLMError(f"LLM 請求失敗: {type(exc).__name__}") from exc

    try:
        text = data["choices"][0]["message"]["content"].strip()
    except (KeyError, IndexError, TypeError) as exc:
        raise LLMError("LLM 回應格式錯誤") from exc
    if not text:
        raise LLMError("LLM 回應為空白")
    return text


def optional_json(system: str, user: str) -> Optional[str]:
    """嘗試取得 LLM 回應，失敗回傳 ``None``（由呼叫端決定退回模板）。"""
    try:
        return complete(system, user)
    except LLMError:
        return None

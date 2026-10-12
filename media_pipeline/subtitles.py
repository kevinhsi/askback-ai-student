"""繁體中文字幕（SRT）產生與解析。"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any, Dict, List


def _ts(seconds: float) -> str:
    if seconds < 0:
        seconds = 0.0
    ms = int(round(seconds * 1000))
    h, ms = divmod(ms, 3600_000)
    m, ms = divmod(ms, 60_000)
    s, ms = divmod(ms, 1000)
    return f"{h:02d}:{m:02d}:{s:02d},{ms:03d}"


def build_srt(cues: List[Dict[str, Any]], out_path: Path | str, *, field_start: str = "subtitle_start",
              field_end: str = "subtitle_end", text_field: str = "text") -> Path:
    """把時間軸 cues 寫成 SRT。"""
    out_path = Path(out_path)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    blocks: List[str] = []
    for i, cue in enumerate(cues, start=1):
        text = str(cue[text_field]).strip()
        if not text:
            continue
        start = float(cue[field_start])
        end = float(cue[field_end])
        if end <= start:
            end = start + 0.5
        blocks.append(f"{i}\n{_ts(start)} --> {_ts(end)}\n{text}\n")
    content = "\n".join(blocks)
    out_path.write_text(content, encoding="utf-8-sig")
    return out_path


_TS_RE = re.compile(r"(\d+):(\d+):(\d+),(\d+)\s*-->\s*(\d+):(\d+):(\d+),(\d+)")


def parse_srt(path: Path | str) -> List[Dict[str, Any]]:
    """解析 SRT，回傳 ``[{index, start, end, text}]``。"""
    raw = Path(path).read_text(encoding="utf-8-sig")
    entries: List[Dict[str, Any]] = []
    for block in re.split(r"\n\s*\n", raw.strip()):
        lines = [ln for ln in block.splitlines() if ln.strip() != ""]
        if len(lines) < 2:
            continue
        i = 0
        if lines[0].strip().isdigit():
            index = int(lines[0].strip())
            i = 1
        else:
            index = len(entries) + 1
        if i >= len(lines):
            continue
        m = _TS_RE.search(lines[i])
        if not m:
            continue
        g = [int(x) for x in m.groups()]
        start = g[0] * 3600 + g[1] * 60 + g[2] + g[3] / 1000
        end = g[4] * 3600 + g[5] * 60 + g[6] + g[7] / 1000
        text = "\n".join(lines[i + 1:]).strip()
        entries.append({"index": index, "start": round(start, 3), "end": round(end, 3), "text": text})
    return entries

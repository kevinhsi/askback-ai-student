"""時間軸規劃：把逐句 TTS 時長轉成場景、字幕與音訊段落。

規格要求影片 30–90 秒；若台詞太短，透過「思考停頓、表情變化、
結尾留白」補足長度，**不重複台詞、不加入教學內容**。
"""

from __future__ import annotations

from typing import Any, Dict, List, Sequence

# 各場景在開口前的思考停頓（秒）——用來呈現「想一想再說」的表情變化
THINK_BEFORE = {
    "intro": 2.4,      # 片頭標題卡
    "problem": 0.7,
    "reasoning": 1.0,
    "doubt": 0.6,
    "recall": 0.8,
    "puzzle": 0.7,
    "ask": 0.6,
}
PAUSE_AFTER = 0.55     # 句與句之間的停頓
OUTRO_TAIL = 4.5       # 結尾留白（困惑地看著畫面）


def _scene_types(line_hints: Sequence[Dict[str, Any]], n: int) -> List[Dict[str, Any]]:
    hints: List[Dict[str, Any]] = []
    fallback_cycle = ["intro", "problem", "reasoning", "doubt", "puzzle", "ask"]
    for i in range(n):
        if i < len(line_hints) and line_hints[i]:
            h = line_hints[i]
            hints.append({"scene": h.get("scene", "doubt"), "expression": h.get("expression", "neutral")})
        else:
            hints.append({"scene": fallback_cycle[i % len(fallback_cycle)], "expression": "neutral"})
    return hints


def _compute(
    cue_durations: Sequence[float],
    hints: Sequence[Dict[str, Any]],
    think: Sequence[float],
    pauses: Sequence[float],
    lead: float,
    tail: float,
    fps: int,
    width: int,
    height: int,
) -> Dict[str, Any]:
    t = 0.0
    scenes: List[Dict[str, Any]] = []
    cues: List[Dict[str, Any]] = []
    n = len(cue_durations)

    for i, dur in enumerate(cue_durations):
        pre = lead if i == 0 else think[i]
        scene_start = t
        audio_start = t + pre
        audio_end = audio_start + dur
        post = tail if i == n - 1 else pauses[i]
        t = audio_end + post
        scene_end = t
        hint = hints[i]
        scene_id = f"scene_{i:02d}"
        scenes.append(
            {
                "id": scene_id,
                "type": hint["scene"],
                "start": round(scene_start, 4),
                "end": round(scene_end, 4),
                "expression": hint["expression"],
                "cue_index": i,
                "think_seconds": round(pre, 4),
            }
        )
        cues.append(
            {
                "index": i,
                "start": round(audio_start, 4),
                "end": round(audio_end, 4),
                "duration": round(dur, 4),
                "pre_silence": round(pre, 4),
                "post_silence": round(post, 4),
                "scene_id": scene_id,
            }
        )

    # 字幕：跟著語音，句間保留一點尾巴但不與下一句重疊
    for i, cue in enumerate(cues):
        if i < n - 1:
            nxt = cues[i + 1]["start"]
            cue["subtitle_start"] = round(cue["start"], 4)
            cue["subtitle_end"] = round(min(cue["end"] + 0.4, nxt - 0.05), 4)
        else:
            cue["subtitle_start"] = round(cue["start"], 4)
            cue["subtitle_end"] = round(cue["end"] + 0.6, 4)

    duration = round(t, 4)
    return {
        "fps": fps,
        "width": width,
        "height": height,
        "duration": duration,
        "scenes": scenes,
        "cues": cues,
    }


def build_timeline(
    cue_durations: Sequence[float],
    line_hints: Sequence[Dict[str, Any]],
    *,
    fps: int = 24,
    width: int = 1280,
    height: int = 720,
    target_min: float = 30.0,
    target_max: float = 90.0,
) -> Dict[str, Any]:
    """建立影片時間軸（場景 + 字幕 + 音訊段落），保證落在 30–90 秒。"""
    if not cue_durations:
        raise ValueError("沒有任何語音片段，無法建立時間軸")
    n = len(cue_durations)
    hints = _scene_types(line_hints, n)
    think = [0.0 if i == 0 else THINK_BEFORE.get(hints[i]["scene"], 0.6) for i in range(n)]
    pauses = [PAUSE_AFTER] * n
    lead = THINK_BEFORE["intro"]
    tail = OUTRO_TAIL

    tl = _compute(cue_durations, hints, think, pauses, lead, tail, fps, width, height)

    # 太短 → 增加思考停頓與結尾留白（不重複台詞）
    if tl["duration"] < target_min:
        deficit = target_min + 1.5 - tl["duration"]
        extra_each = (deficit * 0.65) / n
        think = [v + extra_each for v in think]
        think[0] = think[0] + extra_each
        tail = tail + deficit * 0.35
        tl = _compute(cue_durations, hints, think, pauses, lead, tail, fps, width, height)

    # 太長 → 縮短停頓
    if tl["duration"] > target_max:
        think = [max(0.0, v * 0.4) for v in think]
        think[0] = max(2.0, think[0] * 0.6)
        pauses = [0.3] * n
        tail = 3.0
        tl = _compute(cue_durations, hints, think, pauses, lead, tail, fps, width, height)
    if tl["duration"] > target_max:
        raise ValueError(
            f"影片預估長度 {tl['duration']:.1f}s 超過上限 {target_max}s，請減少台詞或調整目標長度"
        )
    if tl["duration"] < target_min:
        raise ValueError(
            f"影片預估長度 {tl['duration']:.1f}s 低於下限 {target_min}s，無法在不重複台詞下補足"
        )

    tl["target"] = {"min": target_min, "max": target_max}
    tl["lead"] = tl["cues"][0]["pre_silence"]
    tl["tail"] = tl["cues"][-1]["post_silence"]
    return tl


def fit_audio_segments(timeline: Dict[str, Any]) -> List[Dict[str, Any]]:
    """回傳音訊組裝計畫：``[{'kind':'silence'|'cue', ...}]``。

    影片音訊與畫面使用同一份時間軸，確保對齊。
    """
    plan: List[Dict[str, Any]] = []
    for cue in timeline["cues"]:
        plan.append({"kind": "silence", "seconds": cue["pre_silence"]})
        plan.append({"kind": "cue", "index": cue["index"]})
        plan.append({"kind": "silence", "seconds": cue["post_silence"]})
    return plan

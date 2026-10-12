"""把 ``student_question.json`` + 時間軸轉成動畫場景腳本。

動畫內容只呈現 JSON 中既有的：學生角色、迷思陳述、錯誤推理步驟、
題目與學生原話；**不會產生正確解法或教師講解**。
"""

from __future__ import annotations

from typing import Any, Dict, List

from student_simulator.simulator import load_student_question

FOCUS_BUILDERS = {
    "intro": lambda s, mc, text: {
        "kicker": f"{s['student']['name']}的學習筆記",
        "title": s["unit"]["unit_name"],
        "subtitle": f"{s['unit']['subject']} {s['unit']['grade']}{s['unit']['semester']} · {s['unit']['platform']}",
    },
    "problem": lambda s, mc, text: {
        "heading": "題目",
        "lines": [mc["display_problem"]],
        "hint": "小明看了三次",
    },
    "reasoning": lambda s, mc, text: {
        "heading": "我覺得這樣比較合理",
        "statement": mc["statement"],
        "steps": [step["thought"] for step in mc["faulty_reasoning"]],
    },
    "doubt": lambda s, mc, text: {
        "heading": "可是怪怪的…",
        "statement": mc["statement"],
        "lines": ["因為我覺得這樣才合理：" + mc["why_it_feels_right"]],
    },
    "recall": lambda s, mc, text: {
        "heading": "老師好像教過…",
        "lines": [text],
        "hint": "口訣內容小明記不起來",
    },
    "puzzle": lambda s, mc, text: {
        "heading": "蛤？",
        "statement": mc["statement"],
        "lines": [mc["display_problem"]],
    },
    "ask": lambda s, mc, text: {
        "heading": "我想問的問題",
        "lines": [text],
        "statement": mc["sticking_point"],
    },
    "outro": lambda s, mc, text: {
        "title": s["unit"]["unit_name"],
        "lines": ["小明還在想這一題…", "卡關點：" + mc["sticking_point"]],
        "disclaimer": s["provenance"]["disclaimer"],
    },
}


def build_scene_script(student: Dict[str, Any], timeline: Dict[str, Any]) -> Dict[str, Any]:
    """產生動畫場景腳本（含字幕與每場景的畫面重點）。"""
    if isinstance(student, str):
        student = load_student_question(student)

    lines: List[str] = list(student["question"]["lines"])
    cues = timeline["cues"]
    if len(cues) != len(lines):
        raise ValueError(f"字幕 cue 數量 {len(cues)} 與台詞數量 {len(lines)} 不一致")

    mc = student["misconception"]
    scenes: List[Dict[str, Any]] = []
    for scene in timeline["scenes"]:
        idx = scene.get("cue_index")
        text = lines[idx] if idx is not None and 0 <= idx < len(lines) else ""
        builder = FOCUS_BUILDERS.get(scene["type"], FOCUS_BUILDERS["doubt"])
        focus = builder(student, mc, text)
        scenes.append({**scene, "focus": focus, "cue_text": text})

    subtitles = [
        {
            "index": c["index"],
            "text": lines[c["index"]],
            "start": c["subtitle_start"],
            "end": c["subtitle_end"],
        }
        for c in cues
    ]

    return {
        "width": timeline["width"],
        "height": timeline["height"],
        "fps": timeline["fps"],
        "duration": timeline["duration"],
        "badge": student["provenance"]["disclaimer"],
        "disclaimer": student["provenance"]["purpose"],
        "unit": student["unit"],
        "student": student["student"],
        "misconception": {
            "id": mc["id"],
            "sticking_point": mc["sticking_point"],
            "statement": mc["statement"],
            "display_problem": mc["display_problem"],
        },
        "scenes": scenes,
        "cues": timeline["cues"],
        "subtitles": subtitles,
        "lines": lines,
    }

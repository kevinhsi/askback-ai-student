"""學生迷思模擬器：產生小明的提問並輸出 ``student_question.json``。

流程（對應規格第二節第 1–5 步）：
1. 選擇六年級學習單元
2. 選擇具代表性的卡關點與錯誤推理
3. 由 AI 學生小明生成自然的繁體中文提問（LLM 或內建迷思資料庫）
4. 檢查角色口吻、迷思合理性與答案洩漏
5. 儲存為 ``student_question.json``（通過 JSON Schema 驗證）
"""

from __future__ import annotations

import datetime as _dt
import json
import os
import re
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Sequence

import jsonschema

from . import llm as _llm
from .character import CHARACTER, VOICE_STYLE
from .misconceptions import DEFAULT_UNIT_ID, UNITS

SCHEMA_PATH = Path(__file__).resolve().parent.parent / "schemas" / "student_question.schema.json"

_ANSWER_LEAK_PATTERNS = [
    r"正確答案",
    r"正解[是為]",
    r"解答是",
    r"答案是",
    r"應該這樣算",
    r"正確的解法",
    r"正確方法是",
]

SPEAKABLE_ROLES = ("student",)

DEFAULT_USER_PROMPTS = [
    "你先不要急著跳過，再把題目念一次看看條件有沒有看錯？",
    "除了你自己的方法，課本這單元還有教你別的做法嗎？",
    "那你把你的算法一步步講給我聽，我看看你卡在哪裡。",
]

FOLLOWUP_TEMPLATES = [
    "蛤？可是我一直都是這樣算的耶，這樣有哪裡不對嗎？",
    "我不太懂你的意思，可以講得更簡單一點嗎？",
    "我再把題目看一次好了…嗯，還是覺得怪怪的。",
    "好吧，我先記下來，等一下再回頭想這一題。",
]


class AnswerLeakError(RuntimeError):
    """提問內容被判定為洩漏標準解答。"""


class UnitNotFoundError(KeyError):
    """找不到指定的學習單元或迷思。"""


def list_units() -> List[Dict[str, Any]]:
    """列出所有可選學習單元的摘要。"""
    out = []
    for uid, unit in UNITS.items():
        out.append(
            {
                "unit_id": uid,
                "unit_name": unit["unit_name"],
                "subject": unit["subject"],
                "grade": unit["grade"],
                "misconceptions": [m["id"] for m in unit["misconceptions"]],
            }
        )
    return out


def list_misconceptions(unit_id: str) -> List[Dict[str, Any]]:
    unit = UNITS.get(unit_id)
    if unit is None:
        raise UnitNotFoundError(unit_id)
    return [
        {
            "id": m["id"],
            "type": m["type"],
            "sticking_point": m["sticking_point"],
            "statement": m["statement"],
        }
        for m in unit["misconceptions"]
    ]


def check_answer_leak(text: str, forbidden: Sequence[str]) -> Dict[str, Any]:
    """檢查提問是否包含標準解答／正確解法的字樣。"""
    hits: List[str] = []
    for pat in _ANSWER_LEAK_PATTERNS:
        if re.search(pat, text):
            hits.append(pat)
    for term in forbidden:
        if term and term in text:
            hits.append(term)
    return {
        "leaked": bool(hits),
        "checked_terms": sorted(set(list(_ANSWER_LEAK_PATTERNS) + [t for t in forbidden if t])),
        "notes": (
            "未偵測到標準解答或教師講解字樣。"
            if not hits
            else "偵測到可能的答案洩漏字樣: " + ", ".join(sorted(set(hits)))
        ),
    }


def load_schema() -> Dict[str, Any]:
    with open(SCHEMA_PATH, "r", encoding="utf-8") as fh:
        return json.load(fh)


def validate_student_question(data: Dict[str, Any]) -> List[str]:
    """以 JSON Schema 驗證資料，回傳錯誤清單（空 list 代表通過）。"""
    schema = load_schema()
    validator = jsonschema.Draft7Validator(schema)
    errors = sorted(validator.iter_errors(data), key=lambda e: list(e.absolute_path))
    messages = []
    for err in errors:
        path = "/".join(str(p) for p in err.absolute_path) or "(root)"
        messages.append(f"{path}: {err.message}")
    # 額外語意檢查：台詞與動畫提示數量必須一致
    lines = data.get("question", {}).get("lines", [])
    hints = data.get("misconception", {}).get("line_hints") or []
    if hints and len(hints) != len(lines):
        messages.append(
            f"question/lines 與 misconception/line_hints 數量不一致: {len(lines)} vs {len(hints)}"
        )
    return messages


def load_student_question(path: os.PathLike | str) -> Dict[str, Any]:
    """讀取並驗證 student_question.json。"""
    p = Path(path)
    with open(p, "r", encoding="utf-8") as fh:
        data = json.load(fh)
    errors = validate_student_question(data)
    if errors:
        raise ValueError(f"{p} 未通過 schema 驗證: " + "; ".join(errors))
    return data


class StudentSimulator:
    """AI 學生「小明」的迷思模擬器。"""

    def __init__(self, unit_id: Optional[str] = None, mode: str = "auto") -> None:
        self.mode = mode
        self.unit_id = unit_id or DEFAULT_UNIT_ID
        if self.unit_id not in UNITS:
            raise UnitNotFoundError(self.unit_id)
        self.mc_index = 0
        self.turns: List[Dict[str, Any]] = []
        self.generator_info: Dict[str, Any] = {"name": "askback-student-simulator", "mode": "template"}

    # --- 選擇 ---------------------------------------------------------------
    def select_unit(self, unit_id: str) -> Dict[str, Any]:
        if unit_id not in UNITS:
            raise UnitNotFoundError(unit_id)
        self.unit_id = unit_id
        return UNITS[unit_id]

    def select_sticking_point(self, index: int = 0) -> Dict[str, Any]:
        unit = UNITS[self.unit_id]
        if not 0 <= index < len(unit["misconceptions"]):
            raise UnitNotFoundError(f"{self.unit_id}#{index}")
        self.mc_index = index
        return unit["misconceptions"][index]

    @property
    def unit(self) -> Dict[str, Any]:
        return UNITS[self.unit_id]

    @property
    def misconception(self) -> Dict[str, Any]:
        return self.unit["misconceptions"][self.mc_index]

    # --- 台詞生成 -----------------------------------------------------------
    def _llm_lines(self, unit: Dict[str, Any], mc: Dict[str, Any]) -> List[str]:
        system = (
            "你是台灣國小六年級學生小明，正在說出自己對均一教育平台習題的困惑。"
            "只輸出 6-8 行繁體中文口語台詞，每行一句，用台灣小學生口吻（語氣詞：耶、啦、蛤）。"
            "嚴禁出現正確答案、正確解法、老師講解或任何修正自己錯誤的內容；"
            "只能描述自己的錯誤想法與困惑提問。"
            "分數要以中文讀法寫出（例如『七分之四』）。"
        )
        user = (
            f"單元：{unit['subject']} {unit['grade']}{unit['unit_name']}\n"
            f"卡關點：{mc['sticking_point']}\n"
            f"我的錯誤想法：{mc['statement']}\n"
            f"題目：{mc['display_problem']}\n"
            f"我的推理步驟：" + " / ".join(s["thought"] for s in mc["faulty_reasoning"])
        )
        raw = _llm.complete(system, user)
        lines = [ln.strip().strip("「」") for ln in raw.splitlines() if ln.strip()]
        lines = [ln for ln in lines if len(ln) >= 2]
        if len(lines) < 3:
            raise _llm.LLMError("LLM 台詞行數不足")
        return lines

    def generate_question(self) -> Dict[str, Any]:
        """產生通過驗證與答案洩漏檢查的學生提問 JSON。"""
        unit, mc = self.unit, self.misconception
        lines: Optional[List[str]] = None
        mode = "template"
        model: Optional[str] = None
        fallback_reason: Optional[str] = None

        if self.mode in ("auto", "llm") and _llm.llm_configured():
            try:
                lines = self._llm_lines(unit, mc)
                mode = "llm"
                model = os.environ.get("ASKBACK_LLM_MODEL") or "gpt-4o-mini"
            except _llm.LLMError as exc:
                fallback_reason = f"LLM 不可用，退回內建迷思資料庫: {type(exc).__name__}"

        if lines is None:
            lines = list(mc["question_lines"])
            mode = "template"

        leak = check_answer_leak("\n".join(lines), mc["forbidden_answer_terms"])
        if leak["leaked"]:
            if mode == "llm":
                # LLM 洩漏答案 → 退回模板重新生成
                fallback_reason = "LLM 輸出觸發答案洩漏檢查，退回內建迷思資料庫"
                lines = list(mc["question_lines"])
                mode = "template"
                leak = check_answer_leak("\n".join(lines), mc["forbidden_answer_terms"])
            if leak["leaked"]:
                raise AnswerLeakError(leak["notes"])

        self.generator_info = {
            "name": "askback-student-simulator",
            "mode": mode,
            "model": model,
            "fallback_reason": fallback_reason,
        }

        now = _dt.datetime.now().astimezone().replace(microsecond=0).isoformat()
        original_text = "".join(lines)
        hints = mc.get("line_hints") or []

        self.turns = [{"turn": 1, "role": "student", "text": original_text}]

        data: Dict[str, Any] = {
            "schema_version": "1.0",
            "generated_at": now,
            "generator": self.generator_info,
            "unit": {
                "platform": unit["platform"],
                "subject": unit["subject"],
                "grade": unit["grade"],
                "semester": unit["semester"],
                "unit_id": unit["unit_id"],
                "unit_name": unit["unit_name"],
                "unit_code": unit.get("unit_code"),
                "topics": list(unit["topics"]),
            },
            "student": {
                "name": CHARACTER["name"],
                "grade": CHARACTER["grade"],
                "age": CHARACTER["age"],
                "region": CHARACTER["region"],
                "language": CHARACTER["language"],
                "character": {
                    "persona": CHARACTER["persona"],
                    "speech_style": CHARACTER["speech_style"],
                    "vocabulary_notes": CHARACTER["vocabulary_notes"],
                    "avoid": list(CHARACTER["avoid"]),
                },
                "voice": {
                    "locale": VOICE_STYLE["locale"],
                    "style": VOICE_STYLE["style"],
                    "synthetic": True,
                    "note": VOICE_STYLE["note"],
                },
            },
            "misconception": {
                "id": mc["id"],
                "type": mc["type"],
                "sticking_point": mc["sticking_point"],
                "statement": mc["statement"],
                "display_problem": mc["display_problem"],
                "faulty_reasoning": [dict(s) for s in mc["faulty_reasoning"]],
                "why_it_feels_right": mc["why_it_feels_right"],
                "forbidden_answer_terms": list(mc["forbidden_answer_terms"]),
                "unit_id": unit["unit_id"],
                "line_hints": [dict(h) for h in hints],
            },
            "question": {
                "original_text": original_text,
                "lines": lines,
                "tone": mc["tone"],
                "topics": list(unit["topics"]),
                "language": "zh-TW",
            },
            "interaction": {"mode": "single", "turns": self.turns},
            "safety": {
                "answer_leak": leak,
                "scope": [
                    "本階段僅呈現學生迷思與提問",
                    "不產生 AI 教學設計師或 instructional_design.json",
                    "不產生教師端迷思診斷報告",
                    "不生成正確答案或教師講解",
                ],
            },
            "provenance": {
                "ai_generated_student": True,
                "disclaimer": "AI 生成學生示範",
                "purpose": "呈現 AI 學生的迷思、困惑與提問，非真實學生紀錄，也非教學示範答案",
            },
        }

        errors = validate_student_question(data)
        if errors:
            raise ValueError("student_question.json 驗證失敗: " + "; ".join(errors))
        return data

    # --- 多輪互動 -----------------------------------------------------------
    def run_dialogue(
        self,
        user_replies: Optional[Iterable[str]] = None,
        *,
        include_initial: bool = True,
    ) -> List[Dict[str, Any]]:
        """多輪互動：使用者回覆 → 小明的後續反應。

        預設使用內建對話骨架；設定 LLM 時改由 LLM 生成學生回覆。
        回合會寫回 ``self.turns``，供 ``generate_question`` 之後呼叫時
        放入 ``interaction.turns``。
        """
        replies = list(user_replies) if user_replies is not None else list(DEFAULT_USER_PROMPTS)
        if include_initial and not self.turns:
            initial = self.generate_question()
            self.turns = list(initial["interaction"]["turns"])

        turn_no = len(self.turns) + 1
        for i, reply in enumerate(replies):
            self.turns.append({"turn": turn_no, "role": "user", "text": reply.strip()})
            turn_no += 1
            self.turns.append({"turn": turn_no, "role": "student", "text": self._reply(i, reply)})
            turn_no += 1
        return list(self.turns)

    def _reply(self, index: int, _user_text: str) -> str:
        if _llm.llm_configured():
            try:
                text = _llm.complete(
                    "你是台灣國小六年級學生小明，用繁體中文口語簡短回應（1-2 句），"
                    "保持自己的錯誤想法與困惑，禁止給出正確答案或修正自己的錯誤。",
                    f"卡關點：{self.misconception['sticking_point']}\n"
                    f"我的錯誤想法：{self.misconception['statement']}\n"
                    f"對方說：{_user_text}",
                )
                return text
            except _llm.LLMError:
                pass
        return FOLLOWUP_TEMPLATES[index % len(FOLLOWUP_TEMPLATES)]

    # --- 輸出 ---------------------------------------------------------------
    def save(self, data: Dict[str, Any], path: os.PathLike | str) -> Path:
        p = Path(path)
        p.parent.mkdir(parents=True, exist_ok=True)
        with open(p, "w", encoding="utf-8") as fh:
            json.dump(data, fh, ensure_ascii=False, indent=2)
            fh.write("\n")
        return p


def build_student_question(
    unit_id: Optional[str] = None,
    mc_index: int = 0,
    *,
    mode: str = "auto",
    user_replies: Optional[Sequence[str]] = None,
    out_path: Optional[os.PathLike | str] = None,
) -> Dict[str, Any]:
    """一步完成「選單元 → 選卡關點 → 生成提問 → 檢查 →（可選）存檔」。"""
    sim = StudentSimulator(unit_id=unit_id, mode=mode)
    sim.select_sticking_point(mc_index)
    data = sim.generate_question()
    if user_replies:
        sim.run_dialogue(user_replies, include_initial=False)
        data["interaction"] = {
            "mode": "multi",
            "turns": list(sim.turns),
        }
        errors = validate_student_question(data)
        if errors:
            raise ValueError("多輪互動後驗證失敗: " + "; ".join(errors))
    if out_path is not None:
        sim.save(data, out_path)
    return data

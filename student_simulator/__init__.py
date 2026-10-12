"""AskBack AI Student — AI 學生迷思模擬器。

以台灣國小六年級學生「小明」的角色，模擬對均一教育平台學習單元的典型迷思、
錯誤推理與困惑提問，輸出 ``student_question.json``。

本套件只負責「學生迷思與提問」，不產生教學設計、標準解答或教師講解。
"""

from .character import CHARACTER, VOICE_STYLE
from .simulator import (
    AnswerLeakError,
    StudentSimulator,
    build_student_question,
    list_misconceptions,
    list_units,
    load_student_question,
    validate_student_question,
)

__all__ = [
    "CHARACTER",
    "VOICE_STYLE",
    "AnswerLeakError",
    "StudentSimulator",
    "build_student_question",
    "list_misconceptions",
    "list_units",
    "load_student_question",
    "validate_student_question",
]

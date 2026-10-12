"""均一教育平台六年級學習單元與典型迷思資料庫。

此資料庫是「模板模式」的內容來源：當環境沒有可用的 LLM 金鑰時，
學生提問由這裡的迷思骨架 + 角色口吻規則組成，保證輸出仍符合
「學生迷思、錯誤推理、不洩漏答案」的規格。

每個迷思包含：
- sticking_point / statement：卡關點與迷思陳述
- faulty_reasoning：學生腦袋裡的錯誤推理步驟（動畫 thought bubble 素材）
- question_lines：小明的原始口語台詞（TTS 與字幕的唯一來源）
- line_hints：每一句對應的動畫場景與表情
- forbidden_answer_terms：答案洩漏檢查詞（正確解法／正確答案）
"""

from __future__ import annotations

from typing import Any, Dict, List

UNITS: Dict[str, Dict[str, Any]] = {
    "math-g6-frac-div": {
        "platform": "均一教育平台",
        "subject": "數學",
        "grade": "六年級",
        "semester": "下學期",
        "unit_id": "math-g6-frac-div",
        "unit_name": "分數的除法",
        "unit_code": "M6-N-3",
        "topics": ["分數除法", "分數四則運算"],
        "misconceptions": [
            {
                "id": "mc-math-g6-frac-div-01",
                "type": "規則誤用（分子分母分別相除）",
                "sticking_point": "分數除以分數時，不知道該用什麼方法計算",
                "statement": "分數除分數，就是分子除以分子、分母除以分母",
                "display_problem": "七分之四 ÷ 五分之三",
                "faulty_reasoning": [
                    {"step": 1, "thought": "除法就是前面的數跟後面的數對應相除"},
                    {"step": 2, "thought": "分子 4 ÷ 分子 3，分母 7 ÷ 分母 5"},
                    {"step": 3, "thought": "四除以三、七除以五都除不盡，一定是數字太奇怪"},
                ],
                "why_it_feels_right": "分數加減法都是分子跟分子、分母跟分母對應處理，除法應該也一樣",
                "forbidden_answer_terms": [
                    "正確答案",
                    "正解",
                    "解答是",
                    "顛倒相乘",
                    "倒數相乘",
                    "乘以倒數",
                    "二十一分之二十",
                    "20/21",
                    "21分之20",
                ],
                "question_lines": [
                    "我是小明，今天在均一寫數學練習題。",
                    "這一題是七分之四除以五分之三。",
                    "我想了很久，覺得應該分子除以分子，分母除以分母。",
                    "可是四除以三、七除以五，都除不盡耶。",
                    "這樣不就要四捨五入？答案會變得很奇怪。",
                    "老師上次有教過一個特別的口訣，可是我一直覺得那只是硬背，說不通。",
                    "難道是我哪裡搞錯了？還是這一題本來就不能算？",
                    "有沒有人可以告訴我，問題到底出在哪裡？",
                ],
                "line_hints": [
                    {"scene": "intro", "expression": "neutral"},
                    {"scene": "problem", "expression": "curious"},
                    {"scene": "reasoning", "expression": "think"},
                    {"scene": "doubt", "expression": "confused"},
                    {"scene": "doubt", "expression": "worried"},
                    {"scene": "recall", "expression": "think"},
                    {"scene": "puzzle", "expression": "puzzled"},
                    {"scene": "ask", "expression": "hopeful"},
                ],
                "tone": "困惑、有點著急",
            },
        ],
    },
    "math-g6-negative": {
        "platform": "均一教育平台",
        "subject": "數學",
        "grade": "六年級",
        "semester": "下學期",
        "unit_id": "math-g6-negative",
        "unit_name": "正負數的大小比較",
        "unit_code": "M6-N-6",
        "topics": ["正負數", "數線", "大小比較"],
        "misconceptions": [
            {
                "id": "mc-math-g6-negative-01",
                "type": "符號誤解（負號被當成標籤）",
                "sticking_point": "負數比大小時，誤用正數的比較規則",
                "statement": "負數比大小，先看數字本身，3 比 2 大，所以 -3 比 -2 大",
                "display_problem": "-3 和 -2 哪一個比較大？",
                "faulty_reasoning": [
                    {"step": 1, "thought": "先把負號放到旁邊，比較數字 3 和 2"},
                    {"step": 2, "thought": "3 比 2 大，所以 -3 比 -2 大"},
                    {"step": 3, "thought": "可是 -3 度比 -2 度還冷，冷不是代表比較小嗎"},
                ],
                "why_it_feels_right": "正數的比較規則直接套用，負號被當成裝飾而不是數的一部分",
                "forbidden_answer_terms": [
                    "正確答案",
                    "正解",
                    "解答是",
                    "數線越右邊越大",
                    "越靠近零越大",
                    "-2 比 -3 大",
                ],
                "question_lines": [
                    "我是小明，今天在均一看正負數的練習題。",
                    "這一題問的是：負三和負二，哪一個比較大？",
                    "我覺得是負三比較大，因為三本來就比二大啊。",
                    "可是媽媽說零下三度比零下二度還冷耶。",
                    "冷就代表比較小嗎？那我不是算反了？",
                    "那為什麼負號後面的數字，反而可以比較大？",
                    "我到底要比的是數字，還是要比那個負號？",
                    "有沒有人可以告訴我，負數比大小要看哪裡？",
                ],
                "line_hints": [
                    {"scene": "intro", "expression": "neutral"},
                    {"scene": "problem", "expression": "curious"},
                    {"scene": "reasoning", "expression": "confident"},
                    {"scene": "doubt", "expression": "confused"},
                    {"scene": "doubt", "expression": "worried"},
                    {"scene": "puzzle", "expression": "puzzled"},
                    {"scene": "puzzle", "expression": "confused"},
                    {"scene": "ask", "expression": "hopeful"},
                ],
                "tone": "困惑、自我懷疑",
            }
        ],
    },
    "sci-g6-circuit": {
        "platform": "均一教育平台",
        "subject": "自然與生活科技",
        "grade": "六年級",
        "semester": "上學期",
        "unit_id": "sci-g6-circuit",
        "unit_name": "串聯電路與並聯電路",
        "unit_code": "N6-3-2",
        "topics": ["電路", "串聯", "電流"],
        "misconceptions": [
            {
                "id": "mc-sci-g6-circuit-01",
                "type": "直覺模型誤用（電流被消耗）",
                "sticking_point": "串聯電路中燈泡亮度變化的原因",
                "statement": "電流流過燈泡會被用掉，所以串聯的下一顆燈泡拿到的電流比較少",
                "display_problem": "兩顆燈泡串聯，為什麼第二顆比較暗？",
                "faulty_reasoning": [
                    {"step": 1, "thought": "電流就像水，流過第一顆燈泡就被用掉一點"},
                    {"step": 2, "thought": "剩下的電流比較少，第二顆燈泡才會比較暗"},
                    {"step": 3, "thought": "接三顆的話，最後一顆應該完全不會亮"},
                ],
                "why_it_feels_right": "把『用掉就變少』的生活直覺套在電流上，忽略了電池提供的是能量",
                "forbidden_answer_terms": [
                    "正確答案",
                    "正解",
                    "解答是",
                    "電流處處相同",
                    "電荷不會被消耗",
                ],
                "question_lines": [
                    "我是小明，今天在均一看自然課的電路單元。",
                    "課本把兩顆燈泡串起來，說第二顆會比較暗。",
                    "我覺得是電流流過第一顆的時候，被用掉了一些。",
                    "所以剩下的電流比較少，第二顆才會變暗。",
                    "那如果我接三顆、四顆，最後一顆不就完全不會亮了嗎？",
                    "可是我上次把三顆接起來，最後一顆還是亮亮的耶。",
                    "這樣我的想法是不是哪裡不對？還是電池本來就有很多電？",
                    "有沒有人可以告訴我，電流到底會不會被用掉？",
                ],
                "line_hints": [
                    {"scene": "intro", "expression": "neutral"},
                    {"scene": "problem", "expression": "curious"},
                    {"scene": "reasoning", "expression": "think"},
                    {"scene": "doubt", "expression": "confident"},
                    {"scene": "puzzle", "expression": "puzzled"},
                    {"scene": "doubt", "expression": "confused"},
                    {"scene": "puzzle", "expression": "worried"},
                    {"scene": "ask", "expression": "hopeful"},
                ],
                "tone": "困惑、半信半疑",
            }
        ],
    },
    "math-g6-circle-area": {
        "platform": "均一教育平台",
        "subject": "數學",
        "grade": "六年級",
        "semester": "下學期",
        "unit_id": "math-g6-circle-area",
        "unit_name": "圓的周長與面積",
        "unit_code": "M6-G-4",
        "topics": ["圓面積", "圓周長", "3.14"],
        "misconceptions": [
            {
                "id": "mc-math-g6-circle-area-01",
                "type": "公式混淆（周長與面積互換）",
                "sticking_point": "圓面積該用直徑還是半徑、跟周長怎麼分",
                "statement": "圓面積就是 3.14 乘以直徑，跟周長的算法差不多",
                "display_problem": "半徑 5 公分的圓，面積是多少？",
                "faulty_reasoning": [
                    {"step": 1, "thought": "圓的公式就是 3.14 乘以某一條長度"},
                    {"step": 2, "thought": "我把直徑 10 公分 × 3.14 = 31.4"},
                    {"step": 3, "thought": "答案單位寫平方公分，可是數字跟周長好像一樣大"},
                ],
                "why_it_feels_right": "周長和面積都會用到 3.14，公式記混了，而且乘起來的數字很整齊",
                "forbidden_answer_terms": [
                    "正確答案",
                    "正解",
                    "解答是",
                    "78.5",
                    "半徑乘以半徑",
                    "πr",
                    "r×r",
                ],
                "question_lines": [
                    "我是小明，今天在均一寫圓面積的題目。",
                    "題目說：半徑五公分的圓，面積是多少？",
                    "我記得圓的公式就是乘以 3.14 就對了。",
                    "所以我把直徑十公分乘以 3.14，得到三十一點四。",
                    "可是我寫的單位是平方公分，數字卻跟周長差不多大。",
                    "而且我好像忘記要用直徑還是半徑了。",
                    "為什麼我算出來的面積，感覺只是一圈的長度？",
                    "有沒有人可以告訴我，我到底漏了什麼？",
                ],
                "line_hints": [
                    {"scene": "intro", "expression": "neutral"},
                    {"scene": "problem", "expression": "curious"},
                    {"scene": "reasoning", "expression": "confident"},
                    {"scene": "doubt", "expression": "think"},
                    {"scene": "doubt", "expression": "confused"},
                    {"scene": "puzzle", "expression": "puzzled"},
                    {"scene": "puzzle", "expression": "confused"},
                    {"scene": "ask", "expression": "hopeful"},
                ],
                "tone": "困惑、不太確定",
            }
        ],
    },
}

DEFAULT_UNIT_ID = "math-g6-frac-div"

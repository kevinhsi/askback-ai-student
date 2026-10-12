"""小明的角色設定（六年級學生外觀、口吻與聲音風格）。

角色設定同時供動畫（外觀配色）與 TTS（口吻）使用，確保一致性。
"""

CHARACTER = {
    "name": "小明",
    "grade": "六年級",
    "age": 11,
    "region": "台灣",
    "language": "zh-TW",
    "persona": (
        "台灣國小六年級男生，約 11–12 歲，住在城市、就讀公立國小。"
        "好奇心強、愛說話，遇到想不通的題目會自言自語，"
        "不太會藏問題，會直接把腦袋裡的錯誤推理說出來。"
        "對升學有點壓力，但本性單純，會老實承認「我不知道」。"
    ),
    "speech_style": (
        "口語、短句、繁體中文台灣用語；常用「耶、啦、喔、蛤、可是、這樣」等語氣詞；"
        "會重複自己的疑問；會先講自己的做法再講卡住的地方；"
        "句子不會太長，偶爾語氣停頓。"
    ),
    "vocabulary_notes": (
        "使用國小六年級數學／自然科詞彙（分數、除法、分子分母、正負數、電路），"
        "分數以中文讀法念出（例如「七分之四」）。"
    ),
    "avoid": [
        "書面語與成語",
        "教師口吻或解釋正確作法",
        "自我修正成正確答案",
        "過於成熟的用詞（例如『筆者認為』『綜上所述』）",
        "大陸用語（例如『做作业』）",
    ],
    # 動畫視覺一致性（供 animation_generator 使用）
    "visual": {
        "style": "simple_2d_flat",
        "hair_color": "#3B2B24",
        "skin_color": "#FBD7AE",
        "shirt_color": "#F4F7FF",
        "shirt_accent": "#2F5597",
        "pants_color": "#2F3E56",
        "shoe_color": "#20242B",
        "eye_color": "#2B2B2B",
        "outline": "#3A2E27",
        "bag_color": "#C0392B",
        "accent_color": "#FF8A3D",
        "bg_wall": "#EAF1FA",
        "bg_floor": "#D9C7A7",
    },
    "accessories": ["紅色側背包", "深藍色領口的白色運動服"],
}

VOICE_STYLE = {
    "locale": "zh-TW",
    "style": "自然、親切、語速稍快的 11–12 歲學生口吻",
    "synthetic": True,
    "note": "一律使用一般合成語音，不冒充真實兒童或未授權的特定人物聲音。",
}

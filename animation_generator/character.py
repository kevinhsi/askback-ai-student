"""小明的程式化 2D 角色繪製（Pillow）。

外觀固定（髮色、服裝、配色來自 ``student_simulator.character.CHARACTER``），
只透過眉毛、眼神、嘴巴、手勢與附加符號（汗滴、問號）改變表情，
確保全片角色一致性。
"""

from __future__ import annotations

import math
from typing import Any, Dict, Optional, Tuple

from PIL import Image, ImageDraw

from student_simulator.character import CHARACTER

VIS: Dict[str, Any] = CHARACTER["visual"]

# 每種表情的臉部參數
EXPRESSIONS: Dict[str, Dict[str, Any]] = {
    "neutral":   {"brow": (0.0, 0.0), "gaze": (0.10, 0.00), "curve": 0.15, "sweat": False, "hand": "down"},
    "curious":   {"brow": (0.5, 0.5), "gaze": (0.35, -0.10), "curve": 0.25, "sweat": False, "hand": "down"},
    "think":     {"brow": (-0.4, 0.3), "gaze": (0.45, -0.35), "curve": -0.05, "sweat": False, "hand": "chin"},
    "confident": {"brow": (0.1, 0.1), "gaze": (0.20, 0.00), "curve": 0.40, "sweat": False, "hand": "down"},
    "confused":  {"brow": (-0.5, 0.6), "gaze": (0.40, -0.20), "curve": -0.35, "sweat": True, "hand": "chin"},
    "worried":   {"brow": (0.6, -0.5), "gaze": (0.05, 0.35), "curve": -0.55, "sweat": True, "hand": "chin"},
    "puzzled":   {"brow": (-0.6, 0.6), "gaze": (0.45, -0.30), "curve": -0.25, "sweat": True, "hand": "chin"},
    "hopeful":   {"brow": (0.5, 0.5), "gaze": (0.25, -0.15), "curve": 0.35, "sweat": False, "hand": "down"},
}

DEFAULT_EXPR = "neutral"


def expression_params(expr: str) -> Dict[str, Any]:
    return EXPRESSIONS.get(expr, EXPRESSIONS[DEFAULT_EXPR])


def _blend(color: str, other: str, ratio: float) -> Tuple[int, int, int]:
    """把兩種 hex 顏色依 ratio 混合。"""

    def _rgb(c: str) -> Tuple[int, int, int]:
        c = c.lstrip("#")
        return int(c[0:2], 16), int(c[2:4], 16), int(c[4:6], 16)

    a, b = _rgb(color), _rgb(other)
    r = max(0.0, min(1.0, ratio))
    return tuple(int(round(a[i] * (1 - r) + b[i] * r)) for i in range(3))  # type: ignore[return-value]


def draw_student(
    img: Image.Image,
    *,
    t: float,
    expr: str = "neutral",
    mouth: float = 0.0,
    blink: bool = False,
    anchor: Tuple[float, float] = (330.0, 610.0),
    scale: float = 1.0,
    sway: bool = True,
    draw_desk: bool = True,
) -> None:
    """在 ``img`` 上畫出小明（腰部以上 + 桌面）。

    Parameters
    ----------
    t: 目前時間（秒），用於呼吸／搖擺動畫
    expr: 表情名稱（見 :data:`EXPRESSIONS`）
    mouth: 嘴巴開合 0..1（由語音包絡驅動）
    blink: 是否閉眼
    anchor: 身體底部中心點
    scale: 縮放
    sway: 是否加入呼吸搖擺
    """
    d = ImageDraw.Draw(img)
    p = expression_params(expr)
    cfg = VIS
    outline = cfg["outline"]

    ax, ay = anchor
    if sway:
        ax += 3.0 * math.sin(t * 1.15)
        ay += 1.5 * math.sin(t * 0.85 + 0.7)
    s = scale

    torso_w, torso_h = 190 * s, 185 * s
    head_rx, head_ry = 92 * s, 96 * s
    torso_top = ay - torso_h
    head_cx = ax
    head_cy = torso_top - head_ry + 8 * s
    head_box = (head_cx - head_rx, head_cy - head_ry, head_cx + head_rx, head_cy + head_ry)

    # 影子
    d.ellipse([ax - 130 * s, ay - 12 * s, ax + 130 * s, ay + 16 * s], fill=_blend("#000000", cfg["bg_floor"], 0.86))

    # 側背包帶
    # 身體（運動服）
    torso_box = (ax - torso_w / 2, torso_top, ax + torso_w / 2, ay)
    d.rounded_rectangle(torso_box, radius=46 * s, fill=cfg["shirt_color"], outline=outline, width=max(2, int(3 * s)))
    # 領口
    collar_y = torso_top + 6 * s
    d.polygon(
        [(ax - 46 * s, collar_y), (ax, collar_y + 54 * s), (ax + 46 * s, collar_y)],
        fill=cfg["shirt_accent"],
        outline=outline,
    )
    d.polygon(
        [(ax - 46 * s, collar_y), (ax, collar_y + 54 * s), (ax, collar_y)],
        fill=_blend(cfg["shirt_accent"], "#FFFFFF", 0.18),
    )
    # 紅色側背包帶（斜挎）
    d.line(
        [(ax - 52 * s, collar_y + 16 * s), (ax + 58 * s, ay - 34 * s)],
        fill=cfg["bag_color"],
        width=int(14 * s),
    )
    # 扣環
    d.rounded_rectangle(
        [ax - 6 * s, ay - 74 * s, ax + 22 * s, ay - 50 * s],
        radius=6 * s,
        fill=_blend(cfg["bag_color"], "#FFFFFF", 0.25),
        outline=outline,
        width=2,
    )

    # 手臂
    sh_y = torso_top + 46 * s
    left_sh = (ax - torso_w / 2 + 6 * s, sh_y)
    right_sh = (ax + torso_w / 2 - 6 * s, sh_y)
    if p["hand"] == "chin":
        # 手托下巴（思考／困惑）
        elbow = (ax + torso_w / 2 + 26 * s, sh_y + 74 * s)
        wrist = (head_cx + 34 * s, head_cy + head_ry - 14 * s)
        d.line([left_sh, (ax - torso_w / 2 - 16 * s, sh_y + 82 * s), (ax - torso_w / 2 - 4 * s, ay - 24 * s)],
               fill=cfg["shirt_color"], width=int(30 * s), joint="curve")
        d.line([right_sh, elbow, wrist], fill=cfg["shirt_color"], width=int(32 * s), joint="curve")
        d.line([right_sh, elbow, wrist], fill=outline, width=max(1, int(2 * s)), joint="curve")
        d.ellipse([wrist[0] - 20 * s, wrist[1] - 20 * s, wrist[0] + 20 * s, wrist[1] + 20 * s],
                  fill=cfg["skin_color"], outline=outline, width=2)
        d.line([left_sh, (ax - torso_w / 2 - 16 * s, sh_y + 82 * s), (ax - torso_w / 2 - 4 * s, ay - 24 * s)],
               fill=outline, width=max(1, int(2 * s)), joint="curve")
    else:
        for sh, sign in ((left_sh, -1), (right_sh, 1)):
            wrist = (sh[0] + sign * 26 * s, ay - 30 * s)
            d.line([sh, wrist], fill=cfg["shirt_color"], width=int(30 * s), joint="curve")
            d.line([sh, wrist], fill=outline, width=max(1, int(2 * s)), joint="curve")
            d.ellipse([wrist[0] - 17 * s, wrist[1] - 14 * s, wrist[0] + 17 * s, wrist[1] + 20 * s],
                      fill=cfg["skin_color"], outline=outline, width=2)

    # 脖子
    d.rounded_rectangle(
        [head_cx - 26 * s, head_cy + head_ry - 18 * s, head_cx + 26 * s, torso_top + 26 * s],
        radius=12 * s,
        fill=_blend(cfg["skin_color"], "#000000", 0.08),
    )

    # 耳朵
    for sx in (-1, 1):
        ex = head_cx + sx * head_rx
        d.ellipse([ex - 15 * s, head_cy - 6 * s, ex + 15 * s, head_cy + 30 * s],
                  fill=cfg["skin_color"], outline=outline, width=2)

    # 臉
    d.ellipse(head_box, fill=cfg["skin_color"], outline=outline, width=max(2, int(3 * s)))

    # 頭髮：覆蓋頭頂與劉海
    hair = cfg["hair_color"]
    d.pieslice([head_cx - head_rx - 3 * s, head_cy - head_ry - 6 * s,
                head_cx + head_rx + 3 * s, head_cy + head_ry - 16 * s],
               start=180, end=360, fill=hair, outline=outline, width=max(2, int(3 * s)))
    # 劉海（三片）
    fringe_top = head_cy - head_ry + 6 * s
    for i, (off, wdt) in enumerate(((-52, 46), (0, 52), (52, 46))):
        x0 = head_cx + off * s - wdt / 2 * s
        d.polygon(
            [(x0, fringe_top - 6 * s), (x0 + wdt * s, fringe_top - 6 * s),
             (x0 + wdt * s * 0.75, fringe_top + (30 + i * 6) * s), (x0 + wdt * s * 0.2, fringe_top + (44 - i * 4) * s)],
            fill=hair,
        )

    # 眉毛
    eye_y = head_cy + 8 * s
    eye_dx = 40 * s
    brow_dy = 34 * s
    for sign, angle in ((-1, p["brow"][0]), (1, p["brow"][1])):
        bx = head_cx + sign * eye_dx
        lift = angle * 12 * s
        d.line(
            [(bx - 24 * s, eye_y - brow_dy - lift * sign if sign > 0 else eye_y - brow_dy + lift),
             (bx + 24 * s, eye_y - brow_dy + lift if sign > 0 else eye_y - brow_dy - lift)],
            fill=hair,
            width=int(7 * s),
        )

    # 眼睛
    gx, gy = p["gaze"]
    for sign in (-1, 1):
        ex = head_cx + sign * eye_dx
        box = (ex - 17 * s, eye_y - 19 * s, ex + 17 * s, eye_y + 19 * s)
        if blink:
            d.line([(ex - 15 * s, eye_y + 2 * s), (ex + 15 * s, eye_y + 2 * s)],
                   fill=outline, width=int(5 * s))
        else:
            d.ellipse(box, fill="#FFFFFF", outline=outline, width=max(1, int(2 * s)))
            px = ex + gx * 14 * s
            py = eye_y + gy * 12 * s
            d.ellipse([px - 9 * s, py - 10 * s, px + 9 * s, py + 10 * s], fill=cfg["eye_color"])
            d.ellipse([px + 2 * s, py - 7 * s, px + 7 * s, py - 2 * s], fill="#FFFFFF")

    # 鼻子
    d.arc([head_cx - 10 * s, head_cy + 24 * s, head_cx + 10 * s, head_cy + 44 * s],
          start=300, end=60, fill=_blend(cfg["skin_color"], "#000000", 0.35), width=max(2, int(3 * s)))

    # 嘴巴
    m = max(0.0, min(1.0, mouth))
    mouth_y = head_cy + 62 * s
    if m >= 0.10:
        h = (10 + m * 30) * s
        d.ellipse([head_cx - 30 * s, mouth_y - h / 2, head_cx + 30 * s, mouth_y + h / 2],
                  fill="#8C3A3A", outline=outline, width=max(1, int(2 * s)))
        if h > 16 * s:
            d.chord([head_cx - 22 * s, mouth_y - 2 * s, head_cx + 22 * s, mouth_y + h / 2 - 2 * s],
                    start=0, end=180, fill="#E07A7A")
    else:
        curve = p["curve"]
        if curve >= 0:
            d.arc([head_cx - 26 * s, mouth_y - 16 * s + curve * 6 * s,
                   head_cx + 26 * s, mouth_y + 18 * s + curve * 6 * s],
                  start=10, end=170, fill=outline, width=int(5 * s))
        else:
            d.arc([head_cx - 26 * s, mouth_y - 14 * s, head_cx + 26 * s, mouth_y + 16 * s],
                  start=195, end=345, fill=outline, width=int(5 * s))

    # 腮紅（困惑／擔心）
    if p["sweat"]:
        for sign in (-1, 1):
            d.ellipse([head_cx + sign * 76 * s - 14 * s, head_cy + 36 * s,
                       head_cx + sign * 76 * s + 14 * s, head_cy + 52 * s],
                      fill=(245, 168, 150))

    # 汗滴（右上角，週期出現）
    if p["sweat"]:
        phase = (t * 0.7) % 2.4
        if phase < 1.4:
            drop_y = head_cy - head_ry - 6 * s + phase * 22 * s
            sx = head_cx + head_rx - 4 * s
            d.polygon([(sx, drop_y - 20 * s), (sx - 13 * s, drop_y + 4 * s), (sx + 13 * s, drop_y + 4 * s)],
                      fill=(110, 178, 235), outline=(70, 130, 195))
            d.ellipse([sx - 13 * s, drop_y - 12 * s, sx + 13 * s, drop_y + 14 * s],
                      fill=(110, 178, 235), outline=(70, 130, 195))

    # 桌面（放在角色前方，製造在課桌前的感覺）
    if draw_desk:
        desk_top = ay + 4 * s
        d.rounded_rectangle([ax - 250 * s, desk_top, ax + 250 * s, desk_top + 30 * s],
                            radius=8 * s, fill="#C8A165", outline="#8C6B3F", width=3)
        d.rounded_rectangle([ax - 250 * s, desk_top + 30 * s, ax + 250 * s, desk_top + 96 * s],
                            radius=6 * s, fill="#B98F52")
        # 桌上：鉛筆與習作本
        d.rounded_rectangle([ax + 96 * s, desk_top - 26 * s, ax + 210 * s, desk_top + 6 * s],
                            radius=5 * s, fill="#FFFFFF", outline="#9AA6B8", width=2)
        for k in range(3):
            d.line([(ax + 106 * s, desk_top - (18 - k * 7) * s), (ax + 196 * s, desk_top - (18 - k * 7) * s)],
                   fill="#C9D2E0", width=2)
        d.rounded_rectangle([ax - 214 * s, desk_top - 8 * s, ax - 120 * s, desk_top + 6 * s],
                            radius=5 * s, fill="#F2C14E", outline="#B8892B", width=2)
        d.polygon([(ax - 120 * s, desk_top - 8 * s), (ax - 104 * s, desk_top - 1 * s),
                   (ax - 120 * s, desk_top + 6 * s)], fill="#E8D9B5", outline="#7A6540")


def blink_at(t: float, seed: float = 0.0) -> bool:
    """依時間與種子決定目前是否在眨眼（約每 3 秒一次，持續 0.14 秒）。"""
    cycle = (t + seed) % 3.05
    return cycle < 0.14

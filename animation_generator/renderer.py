"""程式化 2D 動畫渲染器（Pillow + FFmpeg）。

把場景腳本渲染成實際的連續畫面（非靜態圖改名），並直接以 rawvideo
餵給 FFmpeg 與語音合成輸出 MP4。

動畫內容只呈現學生的迷思、思考過程、困惑與提問。
"""

from __future__ import annotations

import math
import shutil
import subprocess
from pathlib import Path
from typing import Any, Dict, Iterator, List, Optional, Sequence, Tuple

import numpy as np
from PIL import Image, ImageDraw, ImageFont

from student_simulator.character import CHARACTER

from .character import blink_at, draw_student, expression_params

FFMPEG = shutil.which("ffmpeg") or "ffmpeg"

VIS = CHARACTER["visual"]

FONT_CANDIDATES = {
    "regular": [
        r"C:\Windows\Fonts\msjh.ttc",
        r"C:\Windows\Fonts\msyh.ttc",
        "/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc",
        "/System/Library/Fonts/PingFang.ttc",
    ],
    "bold": [
        r"C:\Windows\Fonts\msjhbd.ttc",
        r"C:\Windows\Fonts\msyeb.ttc",
        "/usr/share/fonts/opentype/noto/NotoSansCJK-Bold.ttc",
    ],
}

_COLORS = {
    "panel": (255, 255, 255),
    "panel_border": (47, 85, 151),
    "ink": (36, 45, 66),
    "muted": (110, 122, 143),
    "accent": (255, 138, 61),
    "accent_dark": (214, 96, 24),
    "bubble": (246, 250, 255),
    "step": (47, 85, 151),
    "sub_bg": (18, 26, 42),
    "sub_fg": (255, 255, 255),
    "badge_bg": (214, 96, 24),
    "badge_fg": (255, 255, 255),
    "pill_bg": (47, 85, 151),
    "pill_fg": (255, 255, 255),
    "warn": (214, 60, 60),
}


def _load_font(path: str, size: int) -> ImageFont.FreeTypeFont:
    return ImageFont.truetype(path, size)


def _resolve_fonts() -> Dict[str, str]:
    resolved: Dict[str, str] = {}
    for key, candidates in FONT_CANDIDATES.items():
        for c in candidates:
            if Path(c).exists():
                resolved[key] = c
                break
        if key not in resolved:
            raise RuntimeError(
                "找不到支援繁體中文的基本字型（嘗試過: " + ", ".join(candidates) + "）"
            )
    return resolved


def _wrap(text: str, font: ImageFont.FreeTypeFont, max_width: int, draw: ImageDraw.ImageDraw) -> List[str]:
    """CJK 逐字換行。"""
    lines: List[str] = []
    cur = ""
    for ch in text:
        if ch == "\n":
            lines.append(cur)
            cur = ""
            continue
        trial = cur + ch
        if draw.textlength(trial, font=font) > max_width and cur:
            lines.append(cur)
            cur = ch
        else:
            cur = trial
    if cur:
        lines.append(cur)
    return lines or [""]


def _rgba(color: Any, alpha: float = 1.0) -> Tuple[int, int, int, int]:
    if isinstance(color, str):
        c = color.lstrip("#")
        color = (int(c[0:2], 16), int(c[2:4], 16), int(c[4:6], 16))
    a = int(round(max(0.0, min(1.0, alpha)) * 255))
    return (color[0], color[1], color[2], a)


def _ease_out(x: float) -> float:
    x = max(0.0, min(1.0, x))
    return 1 - (1 - x) ** 3


class SceneCanvas:
    """負責單一場景的底圖（快取）與每一格畫面的合成。"""

    def __init__(self, script: Dict[str, Any]) -> None:
        self.script = script
        self.W = int(script["width"])
        self.H = int(script["height"])
        self.fps = int(script["fps"])
        self.lines: List[str] = list(script["lines"])
        self.subtitles: List[Dict[str, Any]] = list(script["subtitles"])
        self.fonts_path = _resolve_fonts()
        self.fonts = {
            "title": _load_font(self.fonts_path["bold"], 44),
            "h1": _load_font(self.fonts_path["bold"], 34),
            "h2": _load_font(self.fonts_path["bold"], 27),
            "body": _load_font(self.fonts_path["regular"], 25),
            "small": _load_font(self.fonts_path["regular"], 20),
            "caption": _load_font(self.fonts_path["bold"], 30),
            "badge": _load_font(self.fonts_path["bold"], 21),
            "kicker": _load_font(self.fonts_path["bold"], 22),
        }
        self.panel = (636, 96, 1240, 592)
        self._base_cache: Dict[str, Image.Image] = {}
        self._scene_idx = 0

    # -- 底圖 ---------------------------------------------------------------
    def _room_base(self) -> Image.Image:
        key = "room"
        if key in self._base_cache:
            return self._base_cache[key]
        img = Image.new("RGBA", (self.W, self.H), _rgba(VIS["bg_wall"]))
        d = ImageDraw.Draw(img)
        # 牆面與地板
        d.rectangle([0, 0, self.W, self.H], fill=_rgba(VIS["bg_wall"]))
        d.rectangle([0, int(self.H * 0.83), self.W, self.H], fill=_rgba(VIS["bg_floor"]))
        d.line([(0, int(self.H * 0.83)), (self.W, int(self.H * 0.83))], fill=_rgba((170, 150, 120)), width=4)
        # 窗戶（角色左後方）
        wx0, wy0, wx1, wy1 = 56, 44, 268, 226
        d.rounded_rectangle([wx0, wy0, wx1, wy1], radius=14, fill=_rgba((188, 228, 248)),
                            outline=_rgba((120, 150, 170)), width=5)
        d.ellipse([wx0 + 30, wy0 + 34, wx0 + 108, wy0 + 74], fill=_rgba((255, 255, 255)))
        d.ellipse([wx0 + 78, wy0 + 44, wx0 + 152, wy0 + 80], fill=_rgba((255, 255, 255)))
        d.line([((wx0 + wx1) // 2, wy0), ((wx0 + wx1) // 2, wy1)], fill=_rgba((120, 150, 170)), width=5)
        d.line([(wx0, (wy0 + wy1) // 2), (wx1, (wy0 + wy1) // 2)], fill=_rgba((120, 150, 170)), width=5)
        # 海報（課桌上方）
        d.rounded_rectangle([300, 40, 574, 158], radius=12, fill=_rgba((255, 248, 226)),
                            outline=_rgba((206, 178, 116)), width=4)
        d.text((320, 58), "我的學習筆記", font=self.fonts["h2"], fill=_rgba(_COLORS["ink"]))
        d.text((320, 100), self.script["unit"]["unit_name"], font=self.fonts["body"], fill=_rgba(_COLORS["muted"]))
        # 右側內容面板
        d.rounded_rectangle(self.panel, radius=22, fill=_rgba((255, 255, 255)),
                            outline=_rgba(_COLORS["panel_border"]), width=5)
        d.rounded_rectangle([self.panel[0], self.panel[1], self.panel[0] + 12, self.panel[3]],
                            radius=6, fill=_rgba(_COLORS["accent"]))
        self._base_cache[key] = img
        return img

    def base_for(self, scene: Dict[str, Any]) -> Image.Image:
        return self._room_base()

    # -- 場景查找 -----------------------------------------------------------
    def scene_at(self, t: float) -> Dict[str, Any]:
        scenes = self.script["scenes"]
        i = max(0, min(len(scenes) - 1, self._scene_idx))
        while i + 1 < len(scenes) and t >= scenes[i + 1]["start"]:
            i += 1
        while i > 0 and t < scenes[i]["start"]:
            i -= 1
        self._scene_idx = i
        return scenes[i]

    def cue_for(self, idx: Optional[int]) -> Optional[Dict[str, Any]]:
        if idx is None:
            return None
        for c in self.script["cues"]:
            if c["index"] == idx:
                return c
        return None

    # -- 主繪圖 ------------------------------------------------------------
    def render(self, frame_idx: int, mouth_env: Optional[np.ndarray] = None) -> Image.Image:
        t = frame_idx / float(self.fps)
        scene = self.scene_at(t)
        img = self.base_for(scene).copy()
        layer = Image.new("RGBA", (self.W, self.H), (0, 0, 0, 0))
        fade = _ease_out((t - scene["start"]) / 0.45)

        cue = self.cue_for(scene.get("cue_index"))
        speaking = cue is not None and cue["start"] <= t <= cue["end"]
        expr = self._expression_for(scene, t, cue)
        mouth = 0.0
        if speaking and mouth_env is not None and frame_idx < len(mouth_env):
            mouth = float(mouth_env[frame_idx]) if mouth_env[frame_idx] > 0.12 else 0.0
        blink = blink_at(t, seed=(scene.get("cue_index") or 0) * 0.7)

        # 角色（底圖層，永遠可見）
        draw_student(
            img,
            t=t,
            expr=expr,
            mouth=mouth,
            blink=blink,
            anchor=(330.0, float(self.H) * 0.9 - 80.0),
            scale=1.0,
        )

        # 內容面板
        self._draw_panel_content(layer, scene, t, fade, expr)

        # 情境動態元素
        self._draw_scene_fx(layer, scene, t, fade, expr)

        # 字幕（底層疊上）
        self._draw_subtitle(layer, t)
        # 免責標示（AI 生成學生示範）
        self._draw_badge(layer, t)
        # 左上角單元標籤
        self._draw_pill(layer)

        out = Image.alpha_composite(img, layer)
        return out.convert("RGB")

    # -- 表情 ---------------------------------------------------------------
    def _expression_for(self, scene: Dict[str, Any], t: float, cue: Optional[Dict[str, Any]]) -> str:
        expr = scene.get("expression") or "neutral"
        if cue is None:
            return expr
        if t < cue["start"]:
            return "think" if scene.get("cue_index", 0) > 0 else "curious"
        if t > cue["end"] and scene.get("type") in ("doubt", "puzzle", "ask", "reasoning"):
            return "puzzled" if expr != "puzzled" else "confused"
        return expr

    # -- 面板內容 -----------------------------------------------------------
    def _draw_panel_content(self, layer: Image.Image, scene: Dict[str, Any], t: float,
                            fade: float, expr: str) -> None:
        d = ImageDraw.Draw(layer)
        focus = scene.get("focus", {})
        x0, y0, x1, y1 = self.panel
        inner_x = x0 + 34
        inner_w = (x1 - x0) - 68
        y = y0 + 26

        def put(text: str, font: ImageFont.FreeTypeFont, color: Tuple[int, ...],
                *, dy: int = 8, alpha: float = 1.0, width: int = inner_w, xx: int = inner_x) -> None:
            nonlocal y
            for ln in _wrap(text, font, width, d):
                d.text((xx, y), ln, font=font, fill=_rgba(color, alpha))
                y += int(font.size * 1.35) + dy

        a = fade
        # 標題區塊
        if "kicker" in focus:
            d.text((inner_x, y), focus["kicker"], font=self.fonts["kicker"], fill=_rgba(_COLORS["accent_dark"], a))
            y += 34
        if "heading" in focus:
            d.text((inner_x, y), focus["heading"], font=self.fonts["h2"], fill=_rgba(_COLORS["accent_dark"], a))
            y += 40
            bar_w = int(120 * (0.6 + 0.4 * abs(math.sin(t * 2.2))))
            d.rounded_rectangle([inner_x, y - 8, inner_x + bar_w, y - 3], radius=3, fill=_rgba(_COLORS["accent"], a))
            y += 10

        if "title" in focus:
            put(focus["title"], self.fonts["title"], _COLORS["ink"], dy=6, alpha=a)
            y += 6
        if "subtitle" in focus:
            put(focus["subtitle"], self.fonts["body"], _COLORS["muted"], dy=4, alpha=a)
            y += 10

        # 迷思陳述放在「想法氣泡」中，代表學生原本的錯誤想法
        if focus.get("statement"):
            bubble_top = y - 4
            step_font = self.fonts["body"]
            step_lines = _wrap(focus["statement"], step_font, inner_w - 40, d)
            box_h = int(len(step_lines) * step_font.size * 1.35) + 28
            d.rounded_rectangle([inner_x, bubble_top, inner_x + inner_w, bubble_top + box_h],
                                radius=16, fill=_rgba(_COLORS["bubble"], a),
                                outline=_rgba(_COLORS["panel_border"], a), width=3)
            yy = bubble_top + 14
            for ln in step_lines:
                d.text((inner_x + 20, yy), ln, font=step_font, fill=_rgba(_COLORS["ink"], a))
                yy += int(step_font.size * 1.35)
            y = bubble_top + box_h + 18

        # 錯誤推理步驟（逐字顯示 + 動態箭頭）
        if focus.get("steps"):
            budget = max(0, int((t - scene["start"] - 0.4) / 0.045))
            for i, step in enumerate(focus["steps"]):
                shown = step if budget >= len(step) else step[:budget]
                budget = max(0, budget - len(step))
                num = f"{i + 1}."
                d.ellipse([inner_x, y + 4, inner_x + 26, y + 30], fill=_rgba(_COLORS["step"], a))
                d.text((inner_x + 7, y + 6), str(i + 1), font=self.fonts["small"],
                       fill=_rgba((255, 255, 255), a))
                for j, ln in enumerate(_wrap(shown, self.fonts["body"], inner_w - 40, d)):
                    d.text((inner_x + 38, y), ln, font=self.fonts["body"], fill=_rgba(_COLORS["ink"], a))
                    y += int(self.fonts["body"].size * 1.35)
                y += 6
                if i < len(focus["steps"]) - 1:
                    self._dashed_arrow(d, inner_x + 44, y + 2, y + 16, t, a)
                    y += 20

        # 一般文字段落（打字機）
        if focus.get("lines"):
            budget = max(0, int((t - scene["start"] - 0.35) / 0.05))
            for text in focus["lines"]:
                shown = text if budget >= len(text) else text[:budget]
                budget = max(0, budget - len(text))
                put(shown, self.fonts["body"], _COLORS["ink"], dy=5, alpha=a)
                y += 6

        if focus.get("hint"):
            y += 4
            put(focus["hint"], self.fonts["small"], _COLORS["muted"], dy=4, alpha=a * 0.9)

        if focus.get("disclaimer"):
            y += 10
            d.rounded_rectangle([inner_x, y, inner_x + inner_w, y + 66], radius=12,
                                fill=_rgba((255, 240, 232), a), outline=_rgba(_COLORS["badge_bg"], a), width=3)
            d.text((inner_x + 16, y + 12), focus["disclaimer"], font=self.fonts["h2"],
                   fill=_rgba(_COLORS["badge_bg"], a))
            y += 76

    def _dashed_arrow(self, d: ImageDraw.ImageDraw, x: float, y0: float, y1: float,
                      t: float, alpha: float) -> None:
        dash, gap = 8, 6
        offset = (t * 34) % (dash + gap)
        y = y0 - offset
        while y < y1:
            a0 = max(y, y0)
            a1 = min(y + dash, y1)
            if a1 > a0:
                d.line([(x, a0), (x, a1)], fill=_rgba(_COLORS["accent"], alpha), width=4)
            y += dash + gap

    # -- 情境特效 -----------------------------------------------------------
    def _draw_scene_fx(self, layer: Image.Image, scene: Dict[str, Any], t: float,
                       fade: float, expr: str) -> None:
        d = ImageDraw.Draw(layer)
        kind = scene.get("type")
        a = fade
        head = (330.0, float(self.H) * 0.9 - 80.0 - 185.0 - 96.0 + 8.0)

        # 思考／困惑時的浮動問號
        if kind in ("puzzle", "ask", "doubt"):
            for i, (dx, dy, size) in enumerate(((120, -40, 46), (170, 20, 34), (90, 40, 30))):
                ph = t * 1.4 + i * 1.9
                ox = head[0] + dx + 8 * math.sin(ph)
                oy = head[1] + dy + 10 * math.cos(ph * 0.9)
                font = _load_font(self.fonts_path["bold"], size)
                pulse = 0.55 + 0.45 * abs(math.sin(ph))
                d.text((ox, oy), "?", font=font, fill=_rgba(_COLORS["accent_dark"], a * pulse))
        # 推理時的思考點點
        if kind in ("reasoning", "recall"):
            for i in range(3):
                ph = (t * 2.2 - i * 0.35) % 1.4
                ox = head[0] + 96 + i * 26
                oy = head[1] - 54 - 10 * ph
                r = 7 + 3 * math.sin(ph * 3.14)
                alpha = a * max(0.0, 1.0 - ph)
                d.ellipse([ox - r, oy - r, ox + r, oy + r], fill=_rgba(_COLORS["panel_border"], alpha))
        # 想法指向面板的動態箭頭
        if kind in ("reasoning", "doubt", "puzzle"):
            x_from = head[0] + 132
            x_to = self.panel[0] - 14
            y_mid = head[1] + 46
            dash, gp = 10, 8
            off = (t * 40) % (dash + gp)
            x = x_from - off
            while x < x_to:
                s0 = max(x, x_from)
                s1 = min(x + dash, x_to)
                if s1 > s0:
                    d.line([(s0, y_mid), (s1, y_mid)], fill=_rgba(_COLORS["accent_dark"], a * 0.9), width=5)
                x += dash + gp
            d.polygon([(x_to, y_mid - 12), (x_to + 20, y_mid), (x_to, y_mid + 12)],
                      fill=_rgba(_COLORS["accent_dark"], a * 0.9))
        # 「！」驚嘆（學生卡住的瞬間）
        if kind == "doubt":
            ph = (t - scene["start"]) * 2.0
            if 0.15 < ph < 1.4:
                font = _load_font(self.fonts_path["bold"], 54)
                d.text((head[0] - 140, head[1] - 120 - 8 * ph), "!", font=font,
                       fill=_rgba(_COLORS["warn"], a * (1.4 - ph)))

    # -- 字幕 / 標籤 --------------------------------------------------------
    def _draw_subtitle(self, layer: Image.Image, t: float) -> None:
        cue = None
        for c in self.subtitles:
            if c["start"] <= t <= c["end"]:
                cue = c
                break
        if cue is None:
            return
        d = ImageDraw.Draw(layer)
        text = cue["text"]
        font = self.fonts["caption"]
        tw = d.textlength(text, font=font)
        box_w = min(self.W - 80, tw + 56)
        cx = self.W / 2
        top = self.H - 96
        d.rounded_rectangle([cx - box_w / 2, top, cx + box_w / 2, top + 56],
                            radius=14, fill=_rgba(_COLORS["sub_bg"], 0.82))
        d.text((cx - tw / 2, top + 11), text, font=font, fill=_rgba(_COLORS["sub_fg"]))

    def _draw_badge(self, layer: Image.Image, t: float) -> None:
        d = ImageDraw.Draw(layer)
        text = self.script["badge"]
        font = self.fonts["badge"]
        tw = d.textlength(text, font=font)
        x1 = self.W - 24
        x0 = x1 - (tw + 28)
        y0, y1 = 20, 56
        pulse = 0.9 + 0.1 * math.sin(t * 2.4)
        d.rounded_rectangle([x0, y0, x1, y1], radius=18, fill=_rgba(_COLORS["badge_bg"], pulse),
                            outline=_rgba((255, 255, 255), 0.9), width=2)
        d.text((x0 + 14, y0 + 8), text, font=font, fill=_rgba(_COLORS["badge_fg"]))

    def _draw_pill(self, layer: Image.Image) -> None:
        d = ImageDraw.Draw(layer)
        unit = self.script["unit"]
        text = f"{unit['platform']} · {unit['unit_name']}"
        font = self.fonts["small"]
        tw = d.textlength(text, font=font)
        d.rounded_rectangle([24, 20, 24 + tw + 28, 54], radius=17, fill=_rgba(_COLORS["pill_bg"], 0.88))
        d.text((38, 27), text, font=font, fill=_rgba(_COLORS["pill_fg"]))


def iter_frames(script: Dict[str, Any], mouth_env: Optional[np.ndarray] = None) -> Iterator[Tuple[int, bytes]]:
    """依序產生每一格 RGB24 frame（供渲染與測試使用）。"""
    canvas = SceneCanvas(script)
    n = int(math.ceil(float(script["duration"]) * canvas.fps))
    for i in range(n):
        frame = canvas.render(i, mouth_env)
        yield i, frame.tobytes()


def render_animation_frames(script: Dict[str, Any], mouth_env: Optional[np.ndarray] = None) -> List[bytes]:
    """產生所有影格（注意：長片會佔用記憶體，主要供測試短片使用）。"""
    return [buf for _, buf in iter_frames(script, mouth_env)]


def render_animation(
    script: Dict[str, Any],
    audio_path: Path | str,
    out_path: Path | str,
    *,
    mouth_env: Optional[np.ndarray] = None,
    log: Optional[List[str]] = None,
) -> Dict[str, Any]:
    """渲染動畫並與語音合成為 MP4（FFmpeg）。"""
    out_path = Path(out_path)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    audio_path = Path(audio_path)
    if not audio_path.exists():
        raise FileNotFoundError(f"找不到語音檔: {audio_path}")
    if shutil.which("ffmpeg") is None:
        raise RuntimeError("找不到 ffmpeg，無法編碼影片")

    canvas = SceneCanvas(script)
    W, H, fps = canvas.W, canvas.H, canvas.fps
    n_frames = int(math.ceil(float(script["duration"]) * fps))
    duration = float(script["duration"])

    cmd = [
        FFMPEG, "-y", "-v", "error",
        "-f", "rawvideo", "-pix_fmt", "rgb24", "-s", f"{W}x{H}", "-r", str(fps), "-i", "pipe:0",
        "-i", str(audio_path),
        "-map", "0:v:0", "-map", "1:a:0",
        "-c:v", "libx264", "-preset", "medium", "-crf", "20", "-pix_fmt", "yuv420p",
        "-c:a", "aac", "-b:a", "160k", "-ar", "48000",
        "-t", f"{duration:.3f}",
        "-movflags", "+faststart",
        str(out_path),
    ]
    proc = subprocess.Popen(cmd, stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    assert proc.stdin is not None
    written = 0
    try:
        for _, buf in iter_frames(script, mouth_env):
            proc.stdin.write(buf)
            written += 1
    except BrokenPipeError:
        pass
    finally:
        try:
            proc.stdin.close()
        except BrokenPipeError:
            pass
    stderr = proc.stderr.read().decode("utf-8", "replace") if proc.stderr else ""
    ret = proc.wait(timeout=300)
    if ret != 0:
        raise RuntimeError(f"FFmpeg 編碼失敗（exit {ret}）: {stderr[-600:]}")
    if not out_path.exists() or out_path.stat().st_size < 1024:
        raise RuntimeError("影片輸出失敗或檔案過小")
    if log is not None:
        log.append(f"rendered {written} frames -> {out_path}")
    return {
        "path": str(out_path),
        "frames": written,
        "fps": fps,
        "width": W,
        "height": H,
        "duration": round(duration, 3),
        "bytes": out_path.stat().st_size,
        "ffmpeg": stderr.strip(),
    }

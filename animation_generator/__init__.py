"""AI 學生動畫生成模組。

讀取 ``student_question.json`` 與時間軸，以程式化 2D 繪圖（Pillow）
產生連續動態畫面，再由 FFmpeg 編碼為 MP4。

- 角色：小明（六年級學生），外觀配色來自 ``student_simulator.character``
- 內容：只呈現學生的迷思、思考過程、困惑與提問，不產生正確解法
"""

from .scene_script import build_scene_script
from .renderer import render_animation, render_animation_frames

__all__ = ["build_scene_script", "render_animation", "render_animation_frames"]

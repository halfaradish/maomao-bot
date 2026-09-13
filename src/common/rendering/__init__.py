"""渲染公共层：HTML→图片（Playwright）与 PIL 画图工具。

- BrowserPool：懒启动常驻 Chromium，空闲超时自动关闭，支持 png/jpeg、缩放、全页截图
- picgen：跨平台中文字体加载（带缓存）、文本测量/换行、垂直渐变、圆角矩形

插件用法：

    from src.common.rendering import BrowserPool, get_font
    pool = BrowserPool(idle_timeout=300, tag="my_plugin")
    png = await pool.render("<h1>你好</h1>", width=800)
"""

from .browser import BrowserPool
from .picgen import (
    draw_gradient,
    draw_rounded_rect,
    fit_font_size,
    get_font,
    measure_text,
    wrap_text,
)

__all__ = [
    "BrowserPool",
    "get_font",
    "measure_text",
    "fit_font_size",
    "wrap_text",
    "draw_gradient",
    "draw_rounded_rect",
]

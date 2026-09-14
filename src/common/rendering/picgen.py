"""PIL 画图公共工具：跨平台中文字体加载、文本测量/换行、渐变背景、圆角矩形。

收编自 leaderboard 与 shit_transport 各自维护的 _get_font 及渐变/文本助手，
字体按尺寸做模块级缓存，全进程共享。
"""

import os
import platform
from typing import Dict, List, Tuple

from PIL import ImageDraw, ImageFont
from nonebot import logger

# 各操作系统下依次尝试的中文字体路径（命中即用）
_FONT_PATHS: Dict[str, List[str]] = {
    "windows": [
        "C:/Windows/Fonts/msyh.ttc",       # 微软雅黑
        "C:/Windows/Fonts/msyhbd.ttc",     # 微软雅黑粗体
        "C:/Windows/Fonts/simhei.ttf",     # 黑体
        "C:/Windows/Fonts/simsun.ttc",     # 宋体
        "C:/Windows/Fonts/simkai.ttf",     # 楷体
        "C:/Windows/Fonts/calibri.ttf",
        "arial.ttf",
        "arial.ttc",
    ],
    "linux": [
        "/usr/share/fonts/truetype/noto/NotoSansCJK-Regular.ttc",
        "/usr/share/fonts/truetype/noto/NotoSansCJK-Bold.ttc",
        "/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.otf",
        "/usr/share/fonts/opentype/noto/NotoSansCJK-Bold.otf",
        "/usr/share/fonts/truetype/wqy/wqy-microhei.ttc",
        "/usr/share/fonts/truetype/wqy/wqy-zenhei.ttc",
        "/usr/share/fonts/truetype/wqy/wqy-microhei.ttf",
        "/usr/share/fonts/truetype/wqy/wqy-zenhei.ttf",
        "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
        "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
        "/usr/share/fonts/truetype/liberation/LiberationSans-Regular.ttf",
        "/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf",
        "/usr/share/fonts/TTF/DejaVuSans.ttf",
        "/usr/share/fonts/TTF/DejaVuSans-Bold.ttf",
        "arial.ttf",
        "DejaVuSans.ttf",
    ],
    "darwin": [
        "/System/Library/Fonts/PingFang.ttc",
        "/System/Library/Fonts/STHeiti Light.ttc",
        "/System/Library/Fonts/Arial.ttf",
        "/Library/Fonts/Arial.ttf",
        "arial.ttf",
    ],
}

_font_cache: Dict[int, ImageFont.ImageFont] = {}


def get_font(size: int) -> ImageFont.ImageFont:
    """按尺寸获取跨平台中文字体，带全进程缓存"""
    if size in _font_cache:
        return _font_cache[size]

    font_paths = _FONT_PATHS.get(platform.system().lower(), ["arial.ttf", "arial.ttc", "DejaVuSans.ttf"])
    for font_path in font_paths:
        try:
            if os.path.exists(font_path):
                font = ImageFont.truetype(font_path, size, encoding="utf-8")
                logger.debug(f"加载字体: {font_path} (size={size})")
                _font_cache[size] = font
                return font
        except Exception as e:
            logger.debug(f"字体加载失败 {font_path}: {e}")
            continue

    # 尝试系统默认 arial，最后退回 PIL 内置字体
    try:
        font = ImageFont.truetype("arial", size, encoding="utf-8")
        _font_cache[size] = font
        return font
    except Exception:
        pass

    logger.warning("所有字体加载失败，使用 PIL 默认字体")
    font = ImageFont.load_default()
    _font_cache[size] = font
    return font


def measure_text(draw: ImageDraw.ImageDraw, text: str, font: ImageFont.ImageFont) -> Tuple[int, int]:
    """测量文本渲染后的 (宽, 高)"""
    bbox = draw.textbbox((0, 0), text, font=font)
    return bbox[2] - bbox[0], bbox[3] - bbox[1]


def fit_font_size(
    draw: ImageDraw.ImageDraw,
    text: str,
    max_width: int,
    preferred_size: int,
    min_size: int,
) -> ImageFont.ImageFont:
    """在 [min_size, preferred_size] 内从大到小选择能放下 max_width 的字号"""
    for size in range(preferred_size, min_size - 1, -1):
        font = get_font(size)
        width, _ = measure_text(draw, text, font)
        if width <= max_width:
            return font
    return get_font(min_size)


def wrap_text(
    draw: ImageDraw.ImageDraw,
    text: str,
    font: ImageFont.ImageFont,
    max_width: int,
) -> List[str]:
    """逐字符换行，使每行宽度不超过 max_width"""
    if not text:
        return [""]
    lines: List[str] = []
    current = ""
    for char in text:
        candidate = current + char
        width, _ = measure_text(draw, candidate, font)
        if current and width > max_width:
            lines.append(current)
            current = char
        else:
            current = candidate
    if current:
        lines.append(current)
    return lines or [text]


def draw_gradient(
    draw: ImageDraw.ImageDraw,
    width: int,
    height: int,
    top: Tuple[int, int, int],
    bottom: Tuple[int, int, int],
    alpha: int = 255,
) -> None:
    """逐行绘制从 top 到 bottom 的垂直渐变背景"""
    for y in range(height):
        ratio = y / max(height - 1, 1)
        if alpha < 255:
            color = (
                int(top[0] + (bottom[0] - top[0]) * ratio),
                int(top[1] + (bottom[1] - top[1]) * ratio),
                int(top[2] + (bottom[2] - top[2]) * ratio),
                alpha,
            )
        else:
            color = (
                int(top[0] + (bottom[0] - top[0]) * ratio),
                int(top[1] + (bottom[1] - top[1]) * ratio),
                int(top[2] + (bottom[2] - top[2]) * ratio),
            )
        draw.line([(0, y), (width, y)], fill=color)


def draw_rounded_rect(
    draw: ImageDraw.ImageDraw,
    xy: Tuple[int, int, int, int],
    radius: int,
    fill=None,
    outline=None,
    outline_width: int = 1,
) -> None:
    """绘制圆角矩形"""
    draw.rounded_rectangle(xy, radius=radius, fill=fill, outline=outline, width=outline_width)

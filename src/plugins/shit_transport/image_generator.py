import io
import os
import platform
from typing import Any, Dict, List, Optional, Tuple

from PIL import Image, ImageDraw, ImageFont


class BsCountImageGenerator:
    def __init__(self):
        self._font_cache: Dict[str, ImageFont.ImageFont] = {}
        self.width = 980
        self.padding = 28
        self.card_radius = 16
        self.section_gap = 18
        self.row_gap = 8
        self.header_height = 96
        self.footer_height = 42

    def _get_font(self, size: int) -> ImageFont.ImageFont:
        cache_key = str(size)
        if cache_key in self._font_cache:
            return self._font_cache[cache_key]

        font_paths: List[str] = []
        system = platform.system().lower()
        if system == "windows":
            font_paths = [
                "C:/Windows/Fonts/msyh.ttc",
                "C:/Windows/Fonts/msyhbd.ttc",
                "C:/Windows/Fonts/simhei.ttf",
                "C:/Windows/Fonts/simsun.ttc",
            ]
        elif system == "linux":
            font_paths = [
                "/usr/share/fonts/truetype/noto/NotoSansCJK-Regular.ttc",
                "/usr/share/fonts/truetype/wqy/wqy-microhei.ttc",
                "/usr/share/fonts/truetype/wqy/wqy-zenhei.ttc",
            ]
        elif system == "darwin":
            font_paths = [
                "/System/Library/Fonts/PingFang.ttc",
                "/System/Library/Fonts/STHeiti Light.ttc",
            ]

        for font_path in font_paths:
            try:
                if os.path.exists(font_path):
                    font = ImageFont.truetype(font_path, size, encoding="utf-8")
                    self._font_cache[cache_key] = font
                    return font
            except Exception:
                continue

        font = ImageFont.load_default()
        self._font_cache[cache_key] = font
        return font

    def _measure_text(self, draw: ImageDraw.ImageDraw, text: str, font: ImageFont.ImageFont) -> Tuple[int, int]:
        bbox = draw.textbbox((0, 0), text, font=font)
        return bbox[2] - bbox[0], bbox[3] - bbox[1]

    def _fit_font_size(self, draw: ImageDraw.ImageDraw, text: str, max_width: int, preferred_size: int, min_size: int) -> ImageFont.ImageFont:
        for size in range(preferred_size, min_size - 1, -1):
            font = self._get_font(size)
            width, _ = self._measure_text(draw, text, font)
            if width <= max_width:
                return font
        return self._get_font(min_size)

    def _wrap_text(self, draw: ImageDraw.ImageDraw, text: str, font: ImageFont.ImageFont, max_width: int) -> List[str]:
        if not text:
            return [""]
        lines: List[str] = []
        current = ""
        for char in text:
            candidate = current + char
            width, _ = self._measure_text(draw, candidate, font)
            if current and width > max_width:
                lines.append(current)
                current = char
            else:
                current = candidate
        if current:
            lines.append(current)
        return lines or [text]

    def _draw_rounded_rect(self, draw: ImageDraw.ImageDraw, xy: Tuple[int, int, int, int], radius: int, fill, outline=None, outline_width: int = 1):
        draw.rounded_rectangle(xy, radius=radius, fill=fill, outline=outline, width=outline_width)

    def _estimate_section_height(self, rows: List[Dict[str, Any]], draw: ImageDraw.ImageDraw) -> int:
        title_block_height = 78
        table_header_height = 32
        top_gap = 6
        bottom_gap = 14
        total = title_block_height + table_header_height + top_gap
        for item in rows:
            nickname = str(item.get("nickname") or "未知用户")
            nickname_font = self._fit_font_size(draw, nickname, 450, 27, 17)
            nickname_lines = self._wrap_text(draw, nickname, nickname_font, 450)
            line_height = self._measure_text(draw, "测试", nickname_font)[1]
            row_height = max(70, 18 + len(nickname_lines) * (line_height + 2) + 14)
            total += row_height + self.row_gap
        if not rows:
            total += 44
        return total + bottom_gap

    def _draw_section(self, draw: ImageDraw.ImageDraw, top: int, title: str, subtitle: str, rows: List[Dict[str, Any]], accent_color: Tuple[int, int, int]) -> int:
        section_x1 = self.padding
        section_x2 = self.width - self.padding
        section_y1 = top
        section_height = self._estimate_section_height(rows, draw)
        section_y2 = section_y1 + section_height
        count_col_center_x = section_x2 - 145
        tag_col_center_x = section_x2 - 48

        self._draw_rounded_rect(draw, (section_x1, section_y1, section_x2, section_y2), self.card_radius, fill=(255, 255, 255, 255), outline=(220, 228, 240), outline_width=2)

        title_font = self._get_font(25)
        subtitle_font = self._get_font(15)
        draw.text((section_x1 + 20, section_y1 + 14), title, fill=(15, 23, 42), font=title_font)
        draw.text((section_x1 + 20, section_y1 + 44), subtitle, fill=(100, 116, 139), font=subtitle_font)
        draw.line((section_x1 + 18, section_y1 + 72, section_x2 - 18, section_y1 + 72), fill=(229, 234, 242), width=2)

        y = section_y1 + 84
        if not rows:
            empty_font = self._get_font(20)
            draw.text((section_x1 + 20, y), "暂无记录", fill=(120, 128, 150), font=empty_font)
            return section_y2

        header_font = self._get_font(16)
        rank_header_x = section_x1 + 26
        name_header_x = section_x1 + 140
        count_header_text = "次数"
        tag_header_text = "标签"
        count_header_w, _ = self._measure_text(draw, count_header_text, header_font)
        tag_header_w, _ = self._measure_text(draw, tag_header_text, header_font)
        draw.text((rank_header_x, y), "排名", fill=(100, 116, 139), font=header_font)
        draw.text((name_header_x, y), "用户", fill=(100, 116, 139), font=header_font)
        draw.text((count_col_center_x - count_header_w / 2, y), count_header_text, fill=(100, 116, 139), font=header_font)
        draw.text((tag_col_center_x - tag_header_w / 2, y), tag_header_text, fill=(100, 116, 139), font=header_font)
        y += 30

        for index, item in enumerate(rows, start=1):
            row_x1 = section_x1 + 16
            row_x2 = section_x2 - 16
            nickname = str(item.get("nickname") or "未知用户")
            count = int(item.get("count") or 0)
            action_text = str(item.get("action_text") or "统计")
            rank_text = f"#{index}"
            count_text = f"{count} 次"

            nickname_font = self._fit_font_size(draw, nickname, 450, 27, 17)
            nickname_lines = self._wrap_text(draw, nickname, nickname_font, 450)
            nickname_line_height = self._measure_text(draw, "测试", nickname_font)[1]
            count_font = self._get_font(24)
            row_height = max(70, 18 + len(nickname_lines) * (nickname_line_height + 2) + 12)
            row_y2 = y + row_height

            row_fill = (248, 250, 252) if index % 2 == 1 else (255, 255, 255)
            self._draw_rounded_rect(draw, (row_x1, y, row_x2, row_y2), 12, fill=row_fill, outline=(232, 238, 247), outline_width=1)

            badge_x1 = row_x1 + 12
            badge_x2 = badge_x1 + 68
            badge_y1 = y + (row_height - 34) // 2
            badge_y2 = badge_y1 + 34
            self._draw_rounded_rect(draw, (badge_x1, badge_y1, badge_x2, badge_y2), 10, fill=accent_color)
            rank_font = self._get_font(18)
            rank_w, rank_h = self._measure_text(draw, rank_text, rank_font)
            draw.text((badge_x1 + (68 - rank_w) / 2, badge_y1 + (34 - rank_h) / 2 - 1), rank_text, fill=(255, 255, 255), font=rank_font)

            text_x = row_x1 + 104
            current_text_y = y + 12
            for line in nickname_lines:
                draw.text((text_x, current_text_y), line, fill=(15, 23, 42), font=nickname_font)
                current_text_y += nickname_line_height + 2

            count_w, count_h = self._measure_text(draw, count_text, count_font)
            count_x = count_col_center_x - count_w / 2
            draw.text((count_x, y + (row_height - count_h) / 2 - 2), count_text, fill=(30, 41, 59), font=count_font)

            pill_font = self._get_font(16)
            pill_text = action_text
            pill_w, pill_h = self._measure_text(draw, pill_text, pill_font)
            pill_width = pill_w + 22
            pill_x1 = tag_col_center_x - pill_width / 2
            pill_x2 = tag_col_center_x + pill_width / 2
            pill_y1 = y + (row_height - pill_h - 10) // 2
            pill_y2 = pill_y1 + pill_h + 10
            self._draw_rounded_rect(draw, (pill_x1, pill_y1, pill_x2, pill_y2), 12, fill=(239, 246, 255))
            draw.text((pill_x1 + 11, pill_y1 + 4), pill_text, fill=accent_color, font=pill_font)

            y = row_y2 + self.row_gap

        return section_y2

    def generate_image(self, transmit_rows: List[Dict[str, Any]], post_rows: List[Dict[str, Any]], is_show_all: bool, max_show_count: int) -> bytes:
        temp = Image.new("RGBA", (self.width, 2000), (0, 0, 0, 0))
        temp_draw = ImageDraw.Draw(temp)
        section1_height = self._estimate_section_height(transmit_rows, temp_draw)
        section2_height = self._estimate_section_height(post_rows, temp_draw)
        total_height = self.padding * 2 + self.header_height + section1_height + section2_height + self.section_gap + self.footer_height

        image = Image.new("RGBA", (self.width, total_height), (245, 247, 250, 255))
        draw = ImageDraw.Draw(image)

        for y in range(total_height):
            ratio = y / max(total_height - 1, 1)
            r = int(244 + (250 - 244) * ratio)
            g = int(247 + (250 - 247) * ratio)
            b = int(251 + (253 - 251) * ratio)
            draw.line([(0, y), (self.width, y)], fill=(r, g, b, 255))

        draw.rectangle((0, 0, self.width, 6), fill=(59, 130, 246, 255))

        title_font = self._get_font(34)
        subtitle_font = self._get_font(16)
        title = "搬史统计面板"
        subtitle = f"展示模式：{'全部数据' if is_show_all else f'前 {max_show_count} 名'}    数据类型：搬史排行 / 发史排行"
        draw.text((self.padding, self.padding - 2), title, fill=(15, 23, 42), font=title_font)
        draw.text((self.padding, self.padding + 46), subtitle, fill=(100, 116, 139), font=subtitle_font)

        line_y = self.padding + self.header_height - 16
        draw.line((self.padding, line_y, self.width - self.padding, line_y), fill=(203, 213, 225), width=2)

        section_top = self.padding + self.header_height
        section_bottom = self._draw_section(
            draw,
            section_top,
            "使用 bs 命令的用户",
            "统计主动发起搬史命令的成员排行",
            transmit_rows,
            (59, 130, 246),
        )
        section_top = section_bottom + self.section_gap
        section_bottom = self._draw_section(
            draw,
            section_top,
            "被转发消息的用户",
            "统计被搬运内容来源的成员排行",
            post_rows,
            (99, 102, 241),
        )

        footer_font = self._get_font(14)
        footer = f"共展示 {len(transmit_rows)} 条搬史记录 / {len(post_rows)} 条发史记录"
        draw.text((self.padding, section_bottom + 16), footer, fill=(107, 114, 128), font=footer_font)

        img_bytes = io.BytesIO()
        image.save(img_bytes, format="PNG", optimize=True)
        img_bytes.seek(0)
        return img_bytes.getvalue()

import io
import os
import platform
from typing import Optional
from PIL import Image, ImageDraw, ImageFont
import logging

logger = logging.getLogger(__name__)


class CmdListImageGenerator:
    def __init__(self):
        self._font_cache = {}
        
    def _get_font(self, size: int) -> Optional[ImageFont.ImageFont]:
        cache_key = f"{size}"
        if cache_key in self._font_cache:
            return self._font_cache[cache_key]
        
        font_paths = []
        system = platform.system().lower()
        
        if system == "windows":
            font_paths = [
                "C:/Windows/Fonts/msyh.ttc",
                "C:/Windows/Fonts/simhei.ttf",
                "C:/Windows/Fonts/simsun.ttc",
            ]
        elif system == "linux":
            font_paths = [
                "/usr/share/fonts/truetype/noto/NotoSansCJK-Regular.ttc",
                "/usr/share/fonts/truetype/wqy/wqy-microhei.ttc",
            ]
        elif system == "darwin":
            font_paths = [
                "/System/Library/Fonts/PingFang.ttc",
            ]
        
        for font_path in font_paths:
            try:
                if os.path.exists(font_path):
                    font = ImageFont.truetype(font_path, size, encoding='utf-8')
                    self._font_cache[cache_key] = font
                    return font
            except Exception:
                continue
        
        try:
            font = ImageFont.truetype("arial", size, encoding='utf-8')
            self._font_cache[cache_key] = font
            return font
        except:
            pass
        
        default_font = ImageFont.load_default()
        self._font_cache[cache_key] = default_font
        return default_font
    
    def _draw_rounded_rect(self, draw: ImageDraw.Draw, xy: list, radius: int, fill: str):
        x1, y1, x2, y2 = xy
        draw.rectangle([x1 + radius, y1, x2 - radius, y2], fill=fill)
        draw.rectangle([x1, y1 + radius, x2, y2 - radius], fill=fill)
        draw.ellipse([x1, y1, x1 + radius * 2, y1 + radius * 2], fill=fill)
        draw.ellipse([x2 - radius * 2, y1, x2, y1 + radius * 2], fill=fill)
        draw.ellipse([x1, y2 - radius * 2, x1 + radius * 2, y2], fill=fill)
        draw.ellipse([x2 - radius * 2, y2 - radius * 2, x2, y2], fill=fill)
    
    def generate_image(self) -> Optional[bytes]:
        try:
            all_commands = [
                {"category": "📋 基础命令", "commands": ["/cmd  /命令  /help  /帮助 --- 查看所有命令"]},
                {"category": "🛠️ 实用功能", "commands": [
                    "/考勤 --- 查看考勤情况",
                    "/clipboard --- 剪贴板功能",
                    "/clipboard_md --- Markdown剪贴板功能",
                    "/赞我 --- 给QQ资料卡点赞",
                    "/伪造消息 · 伪消息 --- 生成假消息"
                ]},
                {"category": "🏆 竞赛相关", "commands": [
                    "/contest --- 查看竞赛信息",
                    "/duel --- CF推题",
                    "/开始监控 · monitor · 取消监控 · stop · 监控 --- ICPC过题监控",
                    "/赛时过题 · 过题情况 --- 查询赛时过题情况",
                    "/过题^ · 过题 --- 记录过题",
                    "/过题积分榜 · 积分榜 --- 查看过题排行榜",
                    "/检查过题 · 过题统计 --- 实时过题查询"
                ]},
                {"category": "👥 群管理", "commands": [
                    "/ban · unban · kick --- 群成员管理",
                    "/group --- 群管理功能",
                    "/group_pull --- 群消息转发",
                    "/群统计 --- 群统计功能",
                    "/一键退群 --- 批量退群"
                ]},
                {"category": "💻 技术功能", "commands": [
                    "/sum · summary --- LLM对话记录",
                    "/prd --- PRD功能",
                    "/搬史 · 搬屎 · 转发 --- 搬史功能",
                    "/来点涩图 · 来张涩图 · 来张色图 --- 发送涩图",
                    "/测表格 --- 测试表格生成"
                ]},
                {"category": "⚙️ 系统管理", "commands": [
                    "/rate · 限速启用 · 限速禁用 · 限速紧急停止 · 限速恢复 · 限速状态 · 限速全局 · 限速按群 --- 限速管理",
                    "/todo --- 待办提醒",
                    "/清除缓存 --- 清除群成员缓存"
                ]},
            ]
            
            padding = 30
            category_spacing = 15
            item_spacing = 8
            content_width = 650
            total_width = content_width + padding * 2
            
            header_height = 100
            footer_height = 50
            category_header_height = 40
            item_height = 45
            
            total_items = sum(len(cat["commands"]) for cat in all_commands)
            total_categories = len(all_commands)
            
            content_height = (
                header_height +
                total_categories * category_header_height +
                total_items * item_height +
                (total_categories - 1) * category_spacing +
                (total_items - total_categories) * item_spacing +
                footer_height
            )
            
            img = Image.new('RGB', (total_width, content_height + padding * 2), '#0f1729')
            draw = ImageDraw.Draw(img)
            
            for y in range(content_height + padding * 2):
                ratio = y / (content_height + padding * 2)
                r = int(20 + (10 - 20) * ratio)
                g = int(25 + (15 - 25) * ratio)
                b = int(35 + (20 - 35) * ratio)
                draw.line([(0, y), (total_width, y)], fill=(r, g, b))
            
            font_title = self._get_font(28)
            font_subtitle = self._get_font(16)
            font_category = self._get_font(18)
            font_command = self._get_font(14)
            
            title = "🍊 猫猫 Bot 命令帮助"
            draw.text((padding + 20, padding + 20), title, fill='#ffffff', font=font_title)
            
            subtitle = "WutheringWavesUID 帮助 v3.1.1"
            draw.text((padding + 20, padding + 60), subtitle, fill='#8899aa', font=font_subtitle)
            
            line_y = padding + header_height - 10
            draw.line([padding, line_y, total_width - padding, line_y], fill='#4a90e2', width=2)
            
            current_y = padding + header_height + 10
            
            for category in all_commands:
                self._draw_rounded_rect(draw, [padding, current_y, padding + content_width, current_y + 40], 8, '#2a3f5f')
                draw.text((padding + 15, current_y + 8), category["category"], fill='#ffffff', font=font_category)
                current_y += 40 + item_spacing
                
                for cmd in category["commands"]:
                    self._draw_rounded_rect(draw, [padding, current_y, padding + content_width, current_y + 45], 6, '#1e2d3d')
                    parts = cmd.split('---', 1)
                    if len(parts) == 2:
                        commands = parts[0].strip()
                        desc = parts[1].strip()
                        draw.text((padding + 15, current_y + 8), commands, fill='#7dd3fc', font=font_command)
                        draw.text((padding + 15, current_y + 25), desc, fill='#b0b0b0', font=self._get_font(12))
                    else:
                        draw.text((padding + 15, current_y + 12), cmd, fill='#ffffff', font=font_command)
                    current_y += 45 + item_spacing
                
                current_y += category_spacing - item_spacing
            
            footer_text = "💡 该配置项仅针对个人使用"
            draw.text((padding + 20, content_height + padding - 30), footer_text, fill='#667788', font=font_subtitle)
            
            img_bytes = io.BytesIO()
            img.save(img_bytes, format='PNG', optimize=True)
            img_bytes.seek(0)
            
            logger.info(f"成功生成命令列表图片，大小: {len(img_bytes.getvalue())} 字节")
            return img_bytes.getvalue()
            
        except Exception as e:
            logger.error(f"生成命令列表图片时出错: {e}", exc_info=True)
            return None


def generate_cmd_list_image() -> Optional[bytes]:
    generator = CmdListImageGenerator()
    return generator.generate_image()

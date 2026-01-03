"""
积分榜图片生成模块
提供美观的卡片式积分榜图片生成功能
"""

import io
from typing import List, Dict, Optional
from PIL import Image, ImageDraw, ImageFont
import logging

logger = logging.getLogger(__name__)


class LeaderboardImageGenerator:
    """积分榜图片生成器 - 卡片式设计"""
    
    def __init__(self, config):
        self.config = config
        self._font_cache = {}  # 字体缓存
        
    def _get_font(self, size: int) -> Optional[ImageFont.ImageFont]:
        """获取字体 - 跨平台支持中文，带缓存优化"""
        import platform
        import os
        
        # 检查缓存
        cache_key = f"{size}"
        if cache_key in self._font_cache:
            return self._font_cache[cache_key]
        
        font_paths = []
        
        # 根据操作系统选择字体路径
        system = platform.system().lower()
        
        if system == "windows":
            font_paths = [
                "C:/Windows/Fonts/msyh.ttc",  # 微软雅黑
                "C:/Windows/Fonts/simhei.ttf",  # 黑体
                "C:/Windows/Fonts/simsun.ttc",  # 宋体
                "C:/Windows/Fonts/simkai.ttf",  # 楷体
                "C:/Windows/Fonts/calibri.ttf",
                "arial.ttf",
                "arial.ttc",
            ]
        elif system == "linux":
            font_paths = [
                # 常见的中文字体路径
                "/usr/share/fonts/truetype/noto/NotoSansCJK-Regular.ttc",
                "/usr/share/fonts/truetype/noto/NotoSansCJK-Bold.ttc",
                "/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.otf",
                "/usr/share/fonts/opentype/noto/NotoSansCJK-Bold.otf",
                "/usr/share/fonts/truetype/wqy/wqy-microhei.ttc",
                "/usr/share/fonts/truetype/wqy/wqy-zenhei.ttc",
                "/usr/share/fonts/truetype/wqy/wqy-microhei.ttf",
                "/usr/share/fonts/truetype/wqy/wqy-zenhei.ttf",
                # 系统默认字体
                "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
                "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
                "/usr/share/fonts/truetype/liberation/LiberationSans-Regular.ttf",
                "/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf",
                # 尝试系统字体目录
                "/usr/share/fonts/TTF/DejaVuSans.ttf",
                "/usr/share/fonts/TTF/DejaVuSans-Bold.ttf",
                # 回退到通用字体
                "arial.ttf",
                "DejaVuSans.ttf",
            ]
        elif system == "darwin":  # macOS
            font_paths = [
                "/System/Library/Fonts/PingFang.ttc",
                "/System/Library/Fonts/STHeiti Light.ttc",
                "/System/Library/Fonts/Arial.ttf",
                "/Library/Fonts/Arial.ttf",
                "arial.ttf",
            ]
        else:
            # 未知系统，使用通用字体
            font_paths = [
                "arial.ttf",
                "arial.ttc",
                "DejaVuSans.ttf",
            ]
        
        # 尝试加载字体
        for font_path in font_paths:
            try:
                if os.path.exists(font_path):
                    # 使用encoding参数确保正确加载中文字体
                    font = ImageFont.truetype(font_path, size, encoding='utf-8')
                    logger.info(f"成功加载字体: {font_path}")
                    # 缓存字体
                    self._font_cache[cache_key] = font
                    return font
            except Exception as e:
                logger.debug(f"字体加载失败 {font_path}: {e}")
                continue
        
        # 尝试使用PIL的默认字体查找
        try:
            # 尝试加载系统默认字体
            font = ImageFont.truetype("arial", size, encoding='utf-8')
            logger.info("使用系统默认arial字体")
            self._font_cache[cache_key] = font
            return font
        except:
            pass
        
        # 最后使用PIL默认字体
        logger.warning("所有字体加载失败，使用PIL默认字体")
        default_font = ImageFont.load_default()
        self._font_cache[cache_key] = default_font
        return default_font
    
    def _draw_gradient_background(self, draw: ImageDraw.Draw, width: int, height: int):
        """绘制渐变背景"""
        # 创建从深蓝到黑色的渐变背景
        for y in range(height):
            # 计算渐变颜色
            ratio = y / height
            r = int(26 + (0 - 26) * ratio)  # 从深蓝到黑色
            g = int(26 + (0 - 26) * ratio)
            b = int(46 + (0 - 46) * ratio)
            color = (r, g, b)
            draw.line([(0, y), (width, y)], fill=color)
    
    def _draw_header(self, draw: ImageDraw.Draw, width: int, font_large: ImageFont.ImageFont, font_medium: ImageFont.ImageFont):
        """绘制标题头部"""
        # 主标题
        title = "积分排行榜"
        title_bbox = draw.textbbox((0, 0), title, font=font_large)
        title_width = title_bbox[2] - title_bbox[0]
        draw.text(((width - title_width) // 2, 30), title, fill='#FFFFFF', font=font_large)
        
        # 副标题
        subtitle = "Competitive Programming Leaderboard"
        subtitle_bbox = draw.textbbox((0, 0), subtitle, font=font_medium)
        subtitle_width = subtitle_bbox[2] - subtitle_bbox[0]
        draw.text(((width - subtitle_width) // 2, 70), subtitle, fill='#B0B0B0', font=font_medium)
        
        # 装饰线
        line_y = 100
        draw.line([(width//4, line_y), (3*width//4, line_y)], fill='#4A90E2', width=2)
    
    def _draw_rank_card(self, draw: ImageDraw.Draw, i: int, person: Dict, x: int, y: int, 
                       font_large: ImageFont.ImageFont, font_medium: ImageFont.ImageFont, font_small: ImageFont.ImageFont,
                       max_score: int, card_width: int, card_height: int):
        """绘制单个排名卡片"""
        # 卡片背景颜色
        if i == 1:
            card_color = '#FFD700'  # 金色
            rank_color = '#B8860B'
            text_color = '#000000'
        elif i == 2:
            card_color = '#C0C0C0'  # 银色
            rank_color = '#808080'
            text_color = '#000000'
        elif i == 3:
            card_color = '#CD7F32'  # 铜色
            rank_color = '#8B4513'
            text_color = '#FFFFFF'
        else:
            card_color = '#2C3E50'  # 深蓝灰
            rank_color = '#4A90E2'
            text_color = '#FFFFFF'
        
        # 绘制卡片背景（带圆角效果）
        card_rect = [x, y, x + card_width, y + card_height]
        draw.rectangle(card_rect, fill=card_color, outline='#34495E', width=2)
        
        # 排名数字
        rank_text = f"#{i}"
        rank_bbox = draw.textbbox((0, 0), rank_text, font=font_large)
        rank_width = rank_bbox[2] - rank_bbox[0]
        draw.text((x + 15, y + 15), rank_text, fill=rank_color, font=font_large)
        
        # 姓名
        name = person['realName'][:10]  # 限制姓名长度
        draw.text((x + 15, y + 50), name, fill=text_color, font=font_medium)
        
        # 积分
        score_text = f"{person['totalScore']} 分"
        score_bbox = draw.textbbox((0, 0), score_text, font=font_medium)
        score_width = score_bbox[2] - score_bbox[0]
        draw.text((x + card_width - score_width - 15, y + 15), score_text, fill=text_color, font=font_medium)
        
        # 进度条背景
        bar_x, bar_y = x + 15, y + 80
        bar_width = card_width - 30
        bar_height = 8
        draw.rectangle([bar_x, bar_y, bar_x + bar_width, bar_y + bar_height], 
                      fill='#34495E', outline='#2C3E50')
        
        # 进度条填充
        if max_score > 0:
            progress = person['totalScore'] / max_score
            fill_width = int(bar_width * progress)
            if fill_width > 0:
                draw.rectangle([bar_x, bar_y, bar_x + fill_width, bar_y + bar_height], 
                              fill=rank_color)
        
        # 百分比
        percentage = f"{int(progress * 100)}%"
        percent_bbox = draw.textbbox((0, 0), percentage, font=font_small)
        percent_width = percent_bbox[2] - percent_bbox[0]
        draw.text((x + card_width - percent_width - 15, y + 95), percentage, fill=text_color, font=font_small)
    
    def _draw_footer(self, draw: ImageDraw.Draw, width: int, height: int, 
                    font_small: ImageFont.ImageFont, total_people: int):
        """绘制页脚信息"""
        # 底部信息
        footer_text = f"共 {total_people} 人参与 • 数据实时更新"
        footer_bbox = draw.textbbox((0, 0), footer_text, font=font_small)
        footer_width = footer_bbox[2] - footer_bbox[0]
        draw.text(((width - footer_width) // 2, height - 30), footer_text, 
                 fill='#888888', font=font_small)
    
    def _draw_table(self, draw: ImageDraw.Draw, records: List[Dict], start_x: int, start_y: int,
                   rank_width: int, name_width: int, score_width: int, percentage_width: int,
                   row_height: int, font_medium: ImageFont.ImageFont, font_small: ImageFont.ImageFont):
        """绘制表格"""
        # 表头背景
        header_rect = [start_x, start_y, start_x + rank_width + name_width + score_width + percentage_width, start_y + row_height]
        draw.rectangle(header_rect, fill='#34495E', outline='#4A90E2', width=2)
        
        # 表头文字
        header_y = start_y + row_height // 2 - 8
        
        # 排名列
        rank_text = "排名"
        rank_bbox = draw.textbbox((0, 0), rank_text, font=font_medium)
        rank_text_width = rank_bbox[2] - rank_bbox[0]
        draw.text((start_x + rank_width // 2 - rank_text_width // 2, header_y), rank_text, 
                 fill='#FFFFFF', font=font_medium)
        
        # 姓名列
        name_text = "姓名"
        name_bbox = draw.textbbox((0, 0), name_text, font=font_medium)
        name_text_width = name_bbox[2] - name_bbox[0]
        draw.text((start_x + rank_width + name_width // 2 - name_text_width // 2, header_y), name_text, 
                 fill='#FFFFFF', font=font_medium)
        
        # 积分配列
        score_text = "积分"
        score_bbox = draw.textbbox((0, 0), score_text, font=font_medium)
        score_text_width = score_bbox[2] - score_bbox[0]
        draw.text((start_x + rank_width + name_width + score_width // 2 - score_text_width // 2, header_y), score_text, 
                 fill='#FFFFFF', font=font_medium)
        
        # 百分比列
        percent_text = "占比"
        percent_bbox = draw.textbbox((0, 0), percent_text, font=font_medium)
        percent_text_width = percent_bbox[2] - percent_bbox[0]
        draw.text((start_x + rank_width + name_width + score_width + percentage_width // 2 - percent_text_width // 2, header_y), percent_text, 
                 fill='#FFFFFF', font=font_medium)
        
        # 计算最高分用于百分比计算
        max_score = records[0]['totalScore'] if records else 1
        
        # 绘制数据行
        for i, person in enumerate(records):
            y = start_y + row_height + i * row_height
            
            # 行背景色（交替）
            if i % 2 == 0:
                row_color = '#2C3E50'
            else:
                row_color = '#34495E'
            
            row_rect = [start_x, y, start_x + rank_width + name_width + score_width + percentage_width, y + row_height]
            draw.rectangle(row_rect, fill=row_color, outline='#4A90E2', width=1)
            
            # 排名
            rank = i + 1
            rank_text = f"#{rank}"
            rank_bbox = draw.textbbox((0, 0), rank_text, font=font_small)
            rank_text_width = rank_bbox[2] - rank_bbox[0]
            draw.text((start_x + rank_width // 2 - rank_text_width // 2, y + row_height // 2 - 6), rank_text, 
                     fill='#FFFFFF', font=font_small)
            
            # 姓名
            name = str(person.get('realName', ''))
            name_bbox = draw.textbbox((0, 0), name, font=font_small)
            name_text_width = name_bbox[2] - name_bbox[0]
            # 如果名字太长，截断显示
            if name_text_width > name_width - 10:
                name = name[:10] + "..."
                name_bbox = draw.textbbox((0, 0), name, font=font_small)
                name_text_width = name_bbox[2] - name_bbox[0]
            # 居中对齐，与表头保持一致
            draw.text((start_x + rank_width + name_width // 2 - name_text_width // 2, y + row_height // 2 - 6), name, 
                     fill='#FFFFFF', font=font_small)
            
            # 积分
            score = person.get('totalScore', 0)
            score_text = str(score)
            score_bbox = draw.textbbox((0, 0), score_text, font=font_small)
            score_text_width = score_bbox[2] - score_bbox[0]
            draw.text((start_x + rank_width + name_width + score_width // 2 - score_text_width // 2, y + row_height // 2 - 6), score_text, 
                     fill='#FFFFFF', font=font_small)
            
            # 百分比
            percentage = (score / max_score * 100) if max_score > 0 else 0
            percent_text = f"{percentage:.1f}%"
            percent_bbox = draw.textbbox((0, 0), percent_text, font=font_small)
            percent_text_width = percent_bbox[2] - percent_bbox[0]
            draw.text((start_x + rank_width + name_width + score_width + percentage_width // 2 - percent_text_width // 2, y + row_height // 2 - 6), percent_text, 
                     fill='#FFFFFF', font=font_small)
    
    async def generate_image(self, records: List[Dict]) -> Optional[bytes]:
        """
        生成积分榜图片 - 表格形式，显示所有人员
        
        Args:
            records: 积分记录列表
            
        Returns:
            图片字节数据，失败时返回None
        """
        try:
            if not records:
                logger.warning("没有积分数据，无法生成图片")
                return None
            
            # 按积分排序
            records.sort(key=lambda x: x["totalScore"], reverse=True)
            
            # 计算表格参数
            max_name_length = max([len(str(p.get('realName', ''))) for p in records]) if records else 10
            name_width = max(120, min(250, max_name_length * 12))  # 根据名字长度调整
            
            # 表格列宽
            rank_width = 60
            name_width = name_width
            score_width = 100
            percentage_width = 80
            total_width = rank_width + name_width + score_width + percentage_width
            
            # 行高和边距
            row_height = 35
            header_height = 40
            padding = 20
            
            # 计算图片尺寸
            num_rows = len(records)
            width = total_width + padding * 2
            height = header_height + num_rows * row_height + padding * 2 + 100  # 100为标题区域
            
            # 创建图片
            img = Image.new('RGB', (width, height), '#1a1a2e')
            draw = ImageDraw.Draw(img)
            
            # 绘制渐变背景
            self._draw_gradient_background(draw, width, height)
            
            # 获取字体
            font_large = self._get_font(20)
            font_medium = self._get_font(16)
            font_small = self._get_font(14)
            
            # 绘制标题
            self._draw_header(draw, width, font_large, font_medium)
            
            # 绘制表格
            self._draw_table(draw, records, padding, 100 + padding, 
                           rank_width, name_width, score_width, percentage_width, 
                           row_height, font_medium, font_small)
            
            # 转换为字节
            img_bytes = io.BytesIO()
            img.save(img_bytes, format='PNG', optimize=True)
            img_bytes.seek(0)
            
            logger.info(f"成功生成积分榜图片，大小: {len(img_bytes.getvalue())} 字节")
            return img_bytes.getvalue()
            
        except Exception as e:
            logger.error(f"生成积分榜图片时出错: {e}")
            return None


async def generate_leaderboard_image(records: List[Dict], config) -> Optional[bytes]:
    """
    生成积分榜图片的便捷函数
    
    Args:
        records: 积分记录列表
        config: 配置对象
        
    Returns:
        图片字节数据，失败时返回None
    """
    generator = LeaderboardImageGenerator(config)
    return await generator.generate_image(records)
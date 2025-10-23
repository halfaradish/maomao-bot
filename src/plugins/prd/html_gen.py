#!/usr/bin/env python3
"""
PRD插件HTML图片生成器
使用HTML+CSS生成美观的需求卡片，然后转换为图片
"""

import os
import tempfile
import hashlib
import json
from pathlib import Path
from typing import List, Dict, Optional
from datetime import datetime, timedelta

try:
    from html2image import Html2Image

    HTML2IMAGE_AVAILABLE = True
except ImportError:
    HTML2IMAGE_AVAILABLE = False

from nonebot import logger


class SimpleHTMLImageGenerator:
    """简单的HTML图片生成器"""

    def __init__(self, output_dir: str = "data/pictures", custom_path: str = None,
                 enable_cache: bool = True, cache_dir: str = "cache", cache_expire_days: int = 7):
        # 如果提供了自定义路径，优先使用自定义路径
        if custom_path and custom_path.strip():
            self.output_dir = Path(custom_path)
        else:
            # 使用相对路径，相对于项目根目录
            self.output_dir = Path(output_dir)
        self.output_dir.mkdir(parents=True, exist_ok=True)

        # 缓存相关配置
        self.enable_cache = enable_cache
        self.cache_expire_days = cache_expire_days
        self.cache_dir = self.output_dir / cache_dir
        self.single_cache_dir = self.cache_dir / "single"
        self.batch_cache_dir = self.cache_dir / "batch"

        # 创建缓存目录
        if self.enable_cache:
            self.single_cache_dir.mkdir(parents=True, exist_ok=True)
            self.batch_cache_dir.mkdir(parents=True, exist_ok=True)

        # 检查html2image是否可用
        if not HTML2IMAGE_AVAILABLE:
            logger.warning("html2image库未安装，将只生成HTML文件")

    def _get_status_color(self, finish: bool) -> str:
        """根据完成状态获取颜色"""
        return "#28a745" if finish else "#fd7e14"

    def _get_status_text(self, finish: bool) -> str:
        """根据完成状态获取文本"""
        return "已完成" if finish else "进行中"

    def _get_priority_color(self, priority: str = "medium") -> str:
        """根据优先级获取颜色"""
        priority_colors = {
            "high": "#dc3545",
            "medium": "#ffc107",
            "low": "#28a745"
        }
        return priority_colors.get(priority.lower(), "#6c757d")

    def _get_cache_key(self, requirement: Dict) -> str:
        """生成需求的缓存键值"""
        # 提取影响图片内容的关键字段
        key_data = {
            'content': requirement.get('content', ''),
            'finish': requirement.get('finish', False),
            'assign_to': requirement.get('assign_to', ''),
            'priority': requirement.get('priority', 'medium'),
            'group': requirement.get('group', '其他')
        }

        # 生成JSON字符串并计算MD5哈希
        key_str = json.dumps(key_data, sort_keys=True, ensure_ascii=False)
        return hashlib.md5(key_str.encode('utf-8')).hexdigest()

    def _get_batch_cache_key(self, requirements: List[Dict], page: int = 1) -> str:
        """生成批量需求的缓存键值"""
        # 提取所有需求的关键字段
        key_data = {
            'requirements': [
                {
                    'id': req.get('id'),
                    'content': req.get('content', ''),
                    'finish': req.get('finish', False),
                    'assign_to': req.get('assign_to', ''),
                    'priority': req.get('priority', 'medium'),
                    'group': req.get('group', '其他')
                }
                for req in requirements
            ],
            'page': page
        }

        # 生成JSON字符串并计算MD5哈希
        key_str = json.dumps(key_data, sort_keys=True, ensure_ascii=False)
        return hashlib.md5(key_str.encode('utf-8')).hexdigest()

    def _is_cache_valid(self, cache_file: Path) -> bool:
        """检查缓存文件是否有效（未过期）"""
        if not cache_file.exists():
            return False

        # 检查文件修改时间
        file_time = datetime.fromtimestamp(cache_file.stat().st_mtime)
        expire_time = datetime.now() - timedelta(days=self.cache_expire_days)

        return file_time > expire_time

    def _get_cached_image(self, requirement: Dict, cache_type: str = "single") -> Optional[Path]:
        """获取缓存的图片文件"""
        if not self.enable_cache:
            return None

        cache_key = self._get_cache_key(requirement)
        cache_dir = self.single_cache_dir if cache_type == "single" else self.batch_cache_dir

        # 查找匹配的缓存文件
        for cache_file in cache_dir.glob(f"requirement_{requirement.get('id', 'unknown')}_*.png"):
            if cache_key in cache_file.name and self._is_cache_valid(cache_file):
                logger.info(f"找到有效缓存: {cache_file}")
                return cache_file

        return None

    def _get_cached_batch_image(self, requirements: List[Dict], page: int = 1) -> Optional[Path]:
        """获取批量需求的缓存图片"""
        if not self.enable_cache:
            return None

        cache_key = self._get_batch_cache_key(requirements, page)

        # 查找匹配的缓存文件
        for cache_file in self.batch_cache_dir.glob(f"all_page_{page}_*.png"):
            if cache_key in cache_file.name and self._is_cache_valid(cache_file):
                logger.info(f"找到有效批量缓存: {cache_file}")
                return cache_file

        return None

    def _save_to_cache(self, image_path: Path, requirement: Dict, cache_type: str = "single") -> bool:
        """保存图片到缓存"""
        if not self.enable_cache:
            return False

        try:
            cache_key = self._get_cache_key(requirement)
            cache_dir = self.single_cache_dir if cache_type == "single" else self.batch_cache_dir

            # 生成缓存文件名
            cache_filename = f"requirement_{requirement.get('id', 'unknown')}_{cache_key}.png"
            cache_path = cache_dir / cache_filename

            # 复制文件到缓存目录
            import shutil
            shutil.copy2(image_path, cache_path)

            logger.info(f"图片已缓存: {cache_path}")
            return True
        except Exception as e:
            logger.error(f"缓存保存失败: {e}")
            return False

    def _save_batch_to_cache(self, image_path: Path, requirements: List[Dict], page: int = 1) -> bool:
        """保存批量图片到缓存"""
        if not self.enable_cache:
            return False

        try:
            cache_key = self._get_batch_cache_key(requirements, page)

            # 生成缓存文件名
            cache_filename = f"all_page_{page}_{cache_key}.png"
            cache_path = self.batch_cache_dir / cache_filename

            # 复制文件到缓存目录
            import shutil
            shutil.copy2(image_path, cache_path)

            logger.info(f"批量图片已缓存: {cache_path}")
            return True
        except Exception as e:
            logger.error(f"批量缓存保存失败: {e}")
            return False

    def _invalidate_cache(self, requirement_id: int):
        """清除指定需求的缓存"""
        if not self.enable_cache:
            return

        try:
            # 清除单个需求缓存
            for cache_file in self.single_cache_dir.glob(f"requirement_{requirement_id}_*.png"):
                cache_file.unlink()
                logger.info(f"已清除单个需求缓存: {cache_file}")

            # 清除所有批量缓存（因为批量缓存可能包含该需求）
            for cache_file in self.batch_cache_dir.glob("all_page_*.png"):
                cache_file.unlink()
                logger.info(f"已清除批量缓存: {cache_file}")

        except Exception as e:
            logger.error(f"清除缓存失败: {e}")

    def _generate_single_requirement_html(self, requirement: Dict) -> str:
        """生成单个需求的HTML"""
        status_color = self._get_status_color(requirement.get('finish', False))
        status_text = self._get_status_text(requirement.get('finish', False))
        priority_color = self._get_priority_color(requirement.get('priority', 'medium'))

        # 处理内容换行
        content = requirement.get('content', '').replace('\n', '<br>')

        # 构建标签区域
        tags_html = f"""
        <div class="tags-container">
            <span class="tag tag-group">{requirement.get('group', '其他')}</span>
            <span class="tag tag-status" style="background-color: {status_color}">{status_text}</span>
        </div>
        """

        # 构建元信息区域（只在有内容时显示）
        meta_items = []
        if requirement.get('assign_to'):
            meta_items.append(
                f'<div class="meta-item"><strong>执行人：</strong>{requirement.get("assign_to", "")}</div>')
        if requirement.get('last_modify_by'):
            meta_items.append(
                f'<div class="meta-item"><strong>最后修改：</strong>{requirement.get("last_modify_at", "")} by {requirement.get("last_modify_by", "")}</div>')
        if requirement.get('finish_by') and requirement.get('finish'):
            meta_items.append(
                f'<div class="meta-item"><strong>完成时间：</strong>{requirement.get("finish_at", "")} by {requirement.get("finish_by", "")}</div>')

        meta_html = f'<div class="requirement-meta">{chr(10).join(meta_items)}</div>' if meta_items else ''

        html = f"""
        <div class="requirement-card">
            <div class="card-header">
                <div class="requirement-title-container">
                    <span class="requirement-id">#{requirement.get('id', 'N/A')}</span>
                    <h3 class="requirement-title">{requirement.get('content', '无标题')[:50]}{'...' if len(requirement.get('content', '')) > 50 else ''}</h3>
                </div>
                {tags_html}
            </div>

            <div class="card-body">
                <div class="requirement-details">
                    <p><strong>创建者：</strong>{requirement.get('create_by', '未知')}</p>
                    <p><strong>创建时间：</strong>{requirement.get('create_at', '未知')}</p>
                </div>

                {meta_html}
            </div>
        </div>
        """
        return html

    def _generate_css(self) -> str:
        """生成CSS样式"""
        return """
        <style>
        * {
            margin: 0;
            padding: 0;
            box-sizing: border-box;
        }

        body {
            font-family: 'Microsoft YaHei', 'PingFang SC', 'Helvetica Neue', Arial, sans-serif;
            font-size: 18px;
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
            padding: 20px;
            min-height: 100vh;
        }

        .container {
            max-width: 1200px;
            margin: 0 auto;
            background: white;
            border-radius: 15px;
            box-shadow: 0 20px 40px rgba(0,0,0,0.1);
            overflow: hidden;
        }

        .header {
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
            color: white;
            padding: 30px;
            text-align: center;
        }

        .header h1 {
            font-size: 3.5em;
            margin-bottom: 10px;
            font-weight: 300;
        }

        .header p {
            font-size: 1.6em;
            opacity: 0.9;
        }

        .stats {
            display: flex;
            justify-content: space-around;
            padding: 20px;
            background: #f8f9fa;
            border-bottom: 1px solid #e9ecef;
        }

        .stat-item {
            text-align: center;
        }

        .stat-number {
            font-size: 2.5em;
            font-weight: bold;
            color: #667eea;
        }

        .stat-label {
            color: #6c757d;
            margin-top: 5px;
        }

        .requirements-grid {
            padding: 30px;
        }

        .section-title {
            font-size: 2.3em;
            margin-bottom: 20px;
            color: #333;
            border-left: 4px solid #667eea;
            padding-left: 15px;
        }

        .requirement-card {
            background: white;
            border-radius: 12px;
            box-shadow: 0 4px 15px rgba(0,0,0,0.08);
            margin-bottom: 5px;
            overflow: hidden;
            transition: transform 0.3s ease, box-shadow 0.3s ease;
            border: 1px solid #e9ecef;
        }

        .requirement-card:hover {
            transform: translateY(-5px);
            box-shadow: 0 8px 25px rgba(0,0,0,0.15);
        }

        .card-header {
            display: flex;
            justify-content: space-between;
            align-items: flex-start;
            padding: 15px 20px;
            background: #f8f9fa;
            border-bottom: 1px solid #e9ecef;
            gap: 15px;
        }

        .requirement-title-container {
            display: flex;
            align-items: center;
            gap: 12px;
            flex: 1;
        }

        .requirement-id {
            font-weight: bold;
            color: #667eea;
            font-size: 1.7em;
            background: #f0f2ff;
            padding: 4px 8px;
            border-radius: 6px;
            border: 1px solid #e0e6ff;
            white-space: nowrap;
        }

        .requirement-title {
            color: #333;
            margin: 0;
            font-size: 1.7em;
            line-height: 1.4;
            flex: 1;
        }

        .tags-container {
            display: flex;
            gap: 8px;
            align-items: center;
            flex-shrink: 0;
        }

        .tag {
            padding: 6px 12px;
            border-radius: 20px;
            font-size: 1.3em;
            font-weight: 500;
            white-space: nowrap;
        }

        .tag-group {
            background: #e9ecef;
            color: #495057;
            border: 1px solid #dee2e6;
        }

        .tag-status {
            color: white;
            font-weight: 600;
            text-shadow: 0 1px 2px rgba(0,0,0,0.2);
            box-shadow: 0 2px 4px rgba(0,0,0,0.1);
            position: relative;
            overflow: hidden;
        }

        .tag-status::before {
            content: '';
            position: absolute;
            top: 0;
            left: -100%;
            width: 100%;
            height: 100%;
            background: linear-gradient(90deg, transparent, rgba(255,255,255,0.3), transparent);
            animation: shimmer 2s infinite;
        }

        @keyframes shimmer {
            0% { left: -100%; }
            100% { left: 100%; }
        }

        .card-body {
            padding: 20px;
        }

        .requirement-details {
            margin-bottom: 15px;
        }

        .requirement-details p {
            margin-bottom: 8px;
            color: #666;
            font-size: 1.3em;
        }

        .requirement-meta {
            background: #f8f9fa;
            padding: 15px;
            border-radius: 8px;
            border-left: 4px solid #667eea;
        }

        .requirement-meta .meta-item {
            margin-bottom: 8px;
            color: #555;
            font-size: 1.6em;
            line-height: 1.5;
        }

        .requirement-meta .meta-item:last-child {
            margin-bottom: 0;
        }

        .footer {
            text-align: center;
            padding: 20px;
            color: #6c757d;
            background: #f8f9fa;
            border-top: 1px solid #e9ecef;
        }

        .no-requirements {
            text-align: center;
            padding: 60px 20px;
            color: #6c757d;
        }

        .no-requirements h3 {
            font-size: 2em;
            margin-bottom: 10px;
        }

        @media (max-width: 768px) {
            .stats {
                flex-direction: column;
                gap: 15px;
            }

            .header h1 {
                font-size: 2.5em;
            }

            .requirements-grid {
                padding: 20px;
            }
        }
        </style>
        """

    def generate_requirement_card(self, requirement: Dict) -> Optional[str]:
        """生成单个需求卡片"""
        try:
            # 首先检查缓存
            cached_image = self._get_cached_image(requirement, "single")
            if cached_image:
                logger.info(f"使用缓存图片: {cached_image}")
                return str(cached_image)

            html_content = f"""
            <!DOCTYPE html>
            <html lang="zh-CN">
            <head>
                <meta charset="UTF-8">
                <meta name="viewport" content="width=device-width, initial-scale=1.0">
                <title>需求卡片 #{requirement.get('id', 'N/A')}</title>
                {self._generate_css()}
            </head>
            <body>
                <div class="container">
                    <div class="header">
                        <h1>需求详情</h1>
                        <p>PRD管理系统</p>
                    </div>
                    <div class="requirements-grid">
                        {self._generate_single_requirement_html(requirement)}
                    </div>
                    <div class="footer">
                        <p>生成时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}</p>
                    </div>
                </div>
            </body>
            </html>
            """

            # 生成文件名
            timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
            filename = f"requirement_{requirement.get('id', 'unknown')}_{timestamp}"

            if HTML2IMAGE_AVAILABLE:
                try:
                    # 生成图片
                    logger.info("开始使用html2image生成需求卡片PNG图片...")
                    hti = Html2Image(output_path=str(self.output_dir.absolute()))
                    output_path = self.output_dir / f"{filename}.png"

                    logger.info(f"准备生成需求卡片图片到: {output_path}")
                    logger.info(f"输出目录是否存在: {self.output_dir.exists()}")

                    hti.screenshot(
                        html_str=html_content,
                        save_as=f"{filename}.png",
                        size=(800, 600)
                    )

                    # 检查文件是否真的生成了
                    if output_path.exists():
                        logger.info(f"需求卡片图片生成成功: {output_path}")
                        # 保存到缓存
                        self._save_to_cache(output_path, requirement, "single")
                        return str(output_path)
                    else:
                        logger.error(f"需求卡片图片文件未生成: {output_path}")
                        raise Exception("需求卡片图片文件未生成")

                except Exception as e:
                    logger.error(f"使用html2image生成需求卡片图片失败: {e}")
                    logger.info("回退到生成HTML文件...")
                    # 回退到生成HTML文件
                    html_path = self.output_dir / f"{filename}.html"
                    with open(html_path, 'w', encoding='utf-8') as f:
                        f.write(html_content)

                    logger.info(f"需求卡片HTML生成成功: {html_path}")
                    return str(html_path)
            else:
                # 只生成HTML文件
                html_path = self.output_dir / f"{filename}.html"
                with open(html_path, 'w', encoding='utf-8') as f:
                    f.write(html_content)

                logger.info(f"需求卡片HTML生成成功: {html_path}")
                return str(html_path)

        except Exception as e:
            logger.error(f"生成需求卡片失败: {e}")
            return None

    def _calculate_dynamic_height(self, requirements: List[Dict], max_height: int = 4000) -> int:
        """根据需求数量动态计算图片高度"""
        if not requirements:
            return 600  # 空内容时的最小高度

        # 基础高度：头部 + 统计 + 底部
        base_height = 200 + 100 + 100  # 头部200px + 统计100px + 底部100px

        # 每个分组的标题高度
        groups = set(req.get('group', '其他') for req in requirements)
        group_title_height = len(groups) * 60  # 每个分组标题60px

        # 动态计算每个需求卡片的高度
        total_cards_height = 0
        for req in requirements:
            # 基础卡片高度：头部 + 主体padding + 边框
            card_base_height = 15 + 20 + 20 + 20  # 头部padding + 主体padding + 边框 + margin

            # 标题高度（估算，考虑换行）
            title = req.get('title', '')
            title_lines = max(1, len(title) // 30)  # 每行约30个字符
            title_height = title_lines * 24  # 每行24px

            # 描述高度（估算，考虑换行）
            description = req.get('description', '')
            desc_lines = max(1, len(description) // 50)  # 每行约50个字符
            desc_height = desc_lines * 20  # 每行20px

            # 标签高度
            tags_height = 40  # 标签行高度

            # 总卡片高度
            card_height = card_base_height + title_height + desc_height + tags_height
            total_cards_height += card_height

        # 计算总高度
        total_height = base_height + group_title_height + total_cards_height

        # 设置最小和最大高度限制
        min_height = 800

        calculated_height = max(min_height, min(total_height, max_height))

        logger.info(f"动态计算图片高度: {calculated_height}px (需求数量: {len(requirements)}, 分组数: {len(groups)})")
        return calculated_height

    def _split_requirements_by_height(self, requirements: List[Dict], max_height: int = 4000,
                                      max_per_page: int = None) -> List[List[Dict]]:
        """根据高度和数量限制分割需求列表，按类型分组"""
        if not requirements:
            return []

        # 使用配置参数
        if max_per_page is None:
            max_per_page = self.config.max_requirements_per_page

        # 先按类型分组需求
        grouped_requirements = self._group_requirements_by_type(requirements)

        pages = []
        current_page = []
        current_height = 0

        # 基础高度：头部 + 统计 + 底部（优化后的估算）
        base_height = 150 + 80 + 80  # 头部150px + 统计80px + 底部80px

        # 按类型顺序处理需求
        for group_name, group_requirements in grouped_requirements.items():
            # 逐个添加需求，确保不超出限制
            for req in group_requirements:
                # 计算当前需求的高度
                req_height = self._calculate_single_requirement_height(req)

                # 检查是否需要开始新页面
                if (len(current_page) >= max_per_page or
                        (current_height + req_height + base_height) > max_height):

                    if current_page:  # 如果当前页面有内容，保存它
                        pages.append(current_page)
                        current_page = []
                        current_height = 0

                # 添加需求到当前页
                current_page.append(req)
                current_height += req_height

        # 添加最后一页
        if current_page:
            pages.append(current_page)

        logger.info(f"需求分页完成: 总共{len(requirements)}个需求，分成{len(pages)}页")
        for i, page in enumerate(pages):
            logger.info(f"第{i + 1}页: {len(page)}个需求")

        return pages

    def _calculate_single_requirement_height(self, req: Dict) -> int:
        """计算单个需求卡片的高度（优化后的估算）"""
        # 基础卡片高度：头部 + 主体padding + 边框
        card_base_height = 10 + 15 + 15 + 15  # 头部padding + 主体padding + 边框 + margin

        # 标题高度（估算，考虑换行）
        title = req.get('title', '')
        title_lines = max(1, len(title) // 35)  # 每行约35个字符（增加每行字符数）
        title_height = title_lines * 20  # 每行20px（减少行高）

        # 描述高度（估算，考虑换行）
        description = req.get('description', '')
        desc_lines = max(1, len(description) // 60)  # 每行约60个字符（增加每行字符数）
        desc_height = desc_lines * 16  # 每行16px（减少行高）

        # 标签高度
        tags_height = 30  # 标签行高度（减少）

        # 总卡片高度
        return card_base_height + title_height + desc_height + tags_height

    def _group_requirements_by_type(self, requirements: List[Dict]) -> Dict[str, List[Dict]]:
        """按类型分组需求，只返回有需求的分组"""
        groups = {}
        for req in requirements:
            group_name = req.get('group', '其他')
            if group_name not in groups:
                groups[group_name] = []
            groups[group_name].append(req)

        # 只保留有需求的分组，并按类型名称排序
        filtered_groups = {k: v for k, v in groups.items() if len(v) > 0}
        sorted_groups = dict(sorted(filtered_groups.items()))
        return sorted_groups

    def _split_large_group(self, group_requirements: List[Dict], max_height: int, max_per_page: int) -> List[
        List[Dict]]:
        """分割过大的组"""
        pages = []
        current_page = []

        for req in group_requirements:
            if len(current_page) >= max_per_page:
                pages.append(current_page)
                current_page = []
            current_page.append(req)

        if current_page:
            pages.append(current_page)

        return pages

    def generate_requirements_list_paginated(self, requirements: List[Dict], title: str = "需求列表",
                                             max_height: int = 4000, max_per_page: int = None) -> List[str]:
        """生成分页的需求列表图片"""
        if not requirements:
            # 生成空内容的图片
            empty_result = self.generate_requirements_list([], title)
            return [empty_result] if empty_result else []

        # 使用配置参数
        if max_per_page is None:
            max_per_page = self.config.max_requirements_per_page

        # 分割需求列表
        pages = self._split_requirements_by_height(requirements, max_height, max_per_page)

        if not pages:
            return []

        # 为每一页生成图片
        image_paths = []
        total_pages = len(pages)

        for i, page_requirements in enumerate(pages):
            page_title = f"{title} (第{i + 1}页/共{total_pages}页)"
            page_result = self.generate_requirements_list(page_requirements, page_title, requirements)

            if page_result:
                image_paths.append(page_result)
                logger.info(f"第{i + 1}页图片生成成功: {page_result}")
            else:
                logger.error(f"第{i + 1}页图片生成失败")

        logger.info(f"分页图片生成完成: 共生成{len(image_paths)}张图片")
        return image_paths

    def generate_requirements_list(self, requirements: List[Dict], title: str = "需求列表",
                                   all_requirements: List[Dict] = None) -> Optional[str]:
        """生成需求列表图片"""
        try:
            # 首先检查批量缓存
            if requirements:  # 只有在有需求时才检查缓存
                cached_image = self._get_cached_batch_image(requirements, 1)  # 默认第1页
                if cached_image:
                    logger.info(f"使用批量缓存图片: {cached_image}")
                    return str(cached_image)

            if not requirements:
                html_content = f"""
                <!DOCTYPE html>
                <html lang="zh-CN">
                <head>
                    <meta charset="UTF-8">
                    <meta name="viewport" content="width=device-width, initial-scale=1.0">
                    <title>{title}</title>
                    {self._generate_css()}
                </head>
                <body>
                    <div class="container">
                        <div class="header">
                            <h1>{title}</h1>
                            <p>PRD管理系统</p>
                        </div>
                        <div class="no-requirements">
                            <h3>暂无需求</h3>
                            <p>当前没有任何需求记录</p>
                        </div>
                        <div class="footer">
                            <p>生成时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}</p>
                        </div>
                    </div>
                </body>
                </html>
                """
            else:
                # 统计信息 - 如果有全部需求数据，使用全部数据；否则使用当前页数据
                stats_requirements = all_requirements if all_requirements is not None else requirements
                total_count = len(stats_requirements)
                finished_count = sum(1 for req in stats_requirements if req.get('finish', False))
                unfinished_count = total_count - finished_count

                # 按分组统计 - 只统计当前页面实际显示的分组
                groups = {}
                for req in requirements:  # 使用当前页面的需求，而不是全部需求
                    group = req.get('group', '其他')
                    if group not in groups:
                        groups[group] = {'finished': 0, 'unfinished': 0}
                    if req.get('finish', False):
                        groups[group]['finished'] += 1
                    else:
                        groups[group]['unfinished'] += 1

                # 过滤掉没有需求的分组
                groups = {k: v for k, v in groups.items() if v['finished'] + v['unfinished'] > 0}

                # 生成HTML
                stats_html = f"""
                <div class="stats">
                    <div class="stat-item">
                        <div class="stat-number">{total_count}</div>
                        <div class="stat-label">总需求</div>
                    </div>
                    <div class="stat-item">
                        <div class="stat-number">{finished_count}</div>
                        <div class="stat-label">已完成</div>
                    </div>
                    <div class="stat-item">
                        <div class="stat-number">{unfinished_count}</div>
                        <div class="stat-label">进行中</div>
                    </div>
                </div>
                """

                requirements_html = ""
                for group_name, group_stats in groups.items():
                    group_requirements = [req for req in requirements if req.get('group', '其他') == group_name]

                    # 只显示有需求的分组
                    if len(group_requirements) > 0:
                        # 显示当前页面实际显示的需求数量
                        current_page_count = len(group_requirements)
                        requirements_html += f"""
                        <div class="section-title">{group_name} ({current_page_count}个需求)</div>
                        """
                        for req in group_requirements:
                            requirements_html += self._generate_single_requirement_html(req)

                html_content = f"""
                <!DOCTYPE html>
                <html lang="zh-CN">
                <head>
                    <meta charset="UTF-8">
                    <meta name="viewport" content="width=device-width, initial-scale=1.0">
                    <title>{title}</title>
                    {self._generate_css()}
                </head>
                <body>
                    <div class="container">
                        <div class="header">
                            <h1>{title}</h1>
                            <p>PRD管理系统</p>
                        </div>
                        {stats_html}
                        <div class="requirements-grid">
                            {requirements_html}
                        </div>
                        <div class="footer">
                            <p>生成时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}</p>
                        </div>
                    </div>
                </body>
                </html>
                """

            # 生成文件名
            timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
            filename = f"requirements_list_{timestamp}"

            if HTML2IMAGE_AVAILABLE:
                try:
                    # 动态计算图片高度
                    dynamic_height = self._calculate_dynamic_height(requirements)

                    # 生成图片
                    logger.info(f"开始使用html2image生成PNG图片，动态高度: {dynamic_height}px...")
                    hti = Html2Image(output_path=str(self.output_dir.absolute()))
                    output_path = self.output_dir / f"{filename}.png"

                    logger.info(f"准备生成图片到: {output_path}")
                    logger.info(f"输出目录是否存在: {self.output_dir.exists()}")

                    hti.screenshot(
                        html_str=html_content,
                        save_as=f"{filename}.png",
                        size=(1200, 4000)  # 使用固定高度4000px
                    )

                    # 检查文件是否真的生成了
                    if output_path.exists():
                        logger.info(f"需求列表图片生成成功: {output_path} (高度: 4000px)")
                        # 保存到批量缓存
                        if requirements:  # 只有在有需求时才保存缓存
                            self._save_batch_to_cache(output_path, requirements, 1)
                        return str(output_path)
                    else:
                        logger.error(f"图片文件未生成: {output_path}")
                        raise Exception("图片文件未生成")

                except Exception as e:
                    logger.error(f"使用html2image生成图片失败: {e}")
                    logger.info("回退到生成HTML文件...")
                    # 回退到生成HTML文件
                    html_path = self.output_dir / f"{filename}.html"
                    with open(html_path, 'w', encoding='utf-8') as f:
                        f.write(html_content)

                    logger.info(f"需求列表HTML生成成功: {html_path}")
                    return str(html_path)
            else:
                # 只生成HTML文件
                html_path = self.output_dir / f"{filename}.html"
                with open(html_path, 'w', encoding='utf-8') as f:
                    f.write(html_content)

                logger.info(f"需求列表HTML生成成功: {html_path}")
                return str(html_path)

        except Exception as e:
            logger.error(f"生成需求列表失败: {e}")
            return None

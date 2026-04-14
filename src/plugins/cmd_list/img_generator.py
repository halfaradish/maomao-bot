from nonebot import logger
from typing import List
from pathlib import Path
from playwright.async_api import async_playwright
import sys
import os

# 添加当前目录到Python路径
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from model import PluginUsageInfo

img = None
TEMPLATE_PATH = Path(__file__).parent / "template"
TEMPLATE_FILENAME = "help_template.html"
DETAIL_TEMPLATE_FILENAME = "detail_template.html"

def _html_builder(plugins_data: List[PluginUsageInfo], title: str, desc: str) -> str | None:
    try:
        from jinja2 import Environment, FileSystemLoader
        env = Environment(loader=FileSystemLoader(str(TEMPLATE_PATH)))
        template = env.get_template(TEMPLATE_FILENAME)
        
        # 模板渲染
        html_content = template.render(
            plugins=plugins_data,
            title=title,
            desc=desc
        )

        return html_content
    except ImportError:
        logger.error("未安装 jinja2，请运行 pip install jinja2")
        return None
    except Exception as e:
        logger.error(f"渲染HTML失败: {e}")
        return None
    
def _detail_html_builder(plugin_data: PluginUsageInfo, title: str, desc: str):
    try:
        from jinja2 import Environment, FileSystemLoader
        env = Environment(loader=FileSystemLoader(str(TEMPLATE_PATH)))
        template = env.get_template(DETAIL_TEMPLATE_FILENAME)

        html_content = template.render(
            plugin=plugin_data,
            title=title,
            desc=desc
        )

        return html_content
    except ImportError:
        logger.error("未安装 jinja2，请运行 pip install jinja2")
        return None
    except Exception as e:
        logger.error(f"渲染HTML失败: {e}")
        return None

async def _generate_img(plugins_data: List[PluginUsageInfo]):
    html_content = _html_builder(
        plugins_data=plugins_data,
        title="谛听bot",
        desc="已加载插件列表"
    )
    if not html_content:
        return None

    # 生成后的图片
    global img

    try:
        async with async_playwright() as p:
            # 启动浏览器 (headless=True 适合服务器/机器人环境)
            browser = await p.chromium.launch(headless=True)
            page = await browser.new_page()

            # 设置视口大小（适配留白，保证排版）
            await page.set_viewport_size({"width": 900, "height": 800})

            # 加载 HTML 内容
            await page.set_content(html_content)
        
            # 等待页面渲染完成
            await page.wait_for_load_state("networkidle")
            
            # 全屏截图（返回图片二进制数据）
            img = await page.screenshot(type="png", full_page=True)
            
            await browser.close()
    except Exception as e:
        logger.error(f"生成图片失败: {e}")
    
    # 返回图片二进制数据
    return img if img else None

async def _generate_detail_img(plugin_data: PluginUsageInfo):
    detail_img = None
    
    html_content = _detail_html_builder(
        plugin_data=plugin_data,
        title="插件详情",
        desc=f"{plugin_data.name} 的详细信息"
    )
    if not html_content:
        return None

    try:
        async with async_playwright() as p:
            # 启动浏览器 (headless=True 适合服务器/机器人环境)
            browser = await p.chromium.launch(headless=True)
            page = await browser.new_page()

            # 设置视口大小（适配留白，保证排版）
            await page.set_viewport_size({"width": 900, "height": 800})

            # 加载 HTML 内容
            await page.set_content(html_content)
        
            # 等待页面渲染完成
            await page.wait_for_load_state("networkidle")
            
            # 全屏截图（返回图片二进制数据）
            detail_img = await page.screenshot(type="png", full_page=True)
            
            await browser.close()
    except Exception as e:
        logger.error(f"生成详情图片失败: {e}")
    
    return detail_img

async def get_img(plugins_data: List[PluginUsageInfo]):
    global img
    if not img:
        await _generate_img(plugins_data)

    return img

async def get_detail_img(plugin_data: PluginUsageInfo):
    return await _generate_detail_img(plugin_data)
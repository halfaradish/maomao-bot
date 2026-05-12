import asyncio
from nonebot import logger
from typing import List
from pathlib import Path
from playwright.async_api import async_playwright
from dataclasses import dataclass

@dataclass(eq=False)
class PluginUsageInfo:
    # 插件名称
    name: str
    # 插件功能介绍
    description: str
    # 插件使用方法
    usage: str
    # 插件组别
    group: str | None
    # 颜色点
    badge_color: str | None = None


TEMPLATE_PATH = Path(__file__).parent
TEMPLATE_FILENAME = "help_template.html"

def html_builder(plugins_data: List[PluginUsageInfo], title: str, desc: str) -> str | None:
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

async def generate_img(plugins_data: List[PluginUsageInfo]):
    html_content = html_builder(
        plugins_data=plugins_data,
        title="谛听bot",
        desc="已加载插件列表"
    )
    if not html_content:
        return None

    # 生成后的图片
    img = None

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


# 测试图片生成功能
async def test_generate_img():
    # 创建测试数据
    test_plugins = [
        PluginUsageInfo(
            name="签到",
            description="每日签到获取积分",
            usage="使用方法：/签到",
            group="常用应用"
        ),
        PluginUsageInfo(
            name="翻译",
            description="多语言互译工具",
            usage="使用方法：/翻译 [内容]",
            group="常用应用"
        ),
        PluginUsageInfo(
            name="Pixiv排行",
            description="查看P站每日插画排行",
            usage="使用方法：/pixiv",
            group="常用应用"
        ),
        PluginUsageInfo(
            name="天气查询",
            description="实时天气与未来预报",
            usage="使用方法：/天气 [城市]",
            group="查询应用"
        ),
        PluginUsageInfo(
            name="IP归属地",
            description="查询IP地址物理位置",
            usage="使用方法：/ip [地址]",
            group="查询应用"
        ),
        PluginUsageInfo(
            name="百科",
            description="维基百科/百度百科搜索",
            usage="使用方法：/百科 [关键词]",
            group="查询应用"
        ),
        PluginUsageInfo(
            name="计算器",
            description="简易数学表达式计算",
            usage="使用方法：/计算 1+1",
            group="计算应用",
            badge_color="green"
        ),
        PluginUsageInfo(
            name="群管助手",
            description="禁言、踢人、警告",
            usage="使用方法：/ban @user",
            group="群管应用"
        ),
        # --- 常用应用 ---
        PluginUsageInfo(
            name="点歌",
            description="点歌并发送音乐卡片",
            usage="使用方法：/点歌 [歌名]",
            group="常用应用"
        ),
        PluginUsageInfo(
            name="随机图片",
            description="获取随机二次元/风景图片",
            usage="使用方法：/随机图 [分类]",
            group="常用应用"
        ),
        PluginUsageInfo(
            name="早报",
            description="每日新闻早报推送",
            usage="使用方法：/早报",
            group="常用应用"
        ),
        
        # --- 查询应用 ---
        PluginUsageInfo(
            name="健康码",
            description="查询各地健康码状态",
            usage="使用方法：/健康码 [城市]",
            group="查询应用"
        ),
        PluginUsageInfo(
            name="快递查询",
            description="查询快递物流进度",
            usage="使用方法：/快递 [单号]",
            group="查询应用"
        ),

        # --- 计算应用 ---
        PluginUsageInfo(
            name="汇率转换",
            description="实时汇率换算",
            usage="使用方法：/汇率 100 USD to CNY",
            group="计算应用"
        ),
        PluginUsageInfo(
            name="房贷计算",
            description="计算房贷月供与利息",
            usage="使用方法：/房贷 [金额] [年限]",
            group="计算应用"
        ),

        # --- 群管应用 ---
        PluginUsageInfo(
            name="入群欢迎",
            description="设置新人入群欢迎语",
            usage="使用方法：/setwelcome [内容]",
            group="群管应用"
        ),
        PluginUsageInfo(
            name="关键词回复",
            description="设置自动触发回复",
            usage="使用方法：/addreply [关键词] [回复内容]",
            group="群管应用"
        )
    ]
    
    # 测试图片生成
    img = await generate_img(test_plugins)
    
    # 验证结果
    assert img is not None, "图片生成失败"
    assert isinstance(img, bytes), "图片应为二进制数据"
    assert len(img) > 0, "图片数据为空"
    
    # 保存测试图片
    with open("test_output.png", "wb") as f:
        f.write(img)
    
    print("图片生成测试通过！测试图片已保存为 test_output.png")

if __name__ == "__main__":
    asyncio.run(test_generate_img())

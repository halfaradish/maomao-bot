import random
import aiohttp
import urllib.parse
from typing import List, Dict, Any, Optional

from nonebot import on_command, get_driver
from nonebot.rule import Rule
from nonebot.plugin import PluginMetadata
from nonebot.adapters.onebot.v11 import MessageSegment, Message, MessageEvent
from nonebot.log import logger
import re

__plugin_meta__ = PluginMetadata(
    name="PigSender",
    description="从 pighub.top 获取随机猪猪图片",
    usage="指令：来张猪猪 / 随机猪猪 / 来只XX猪（如：来只粉色猪）",
    config=None,
    extra={
        "author": "xqcherry",
        "version": "0.3.2"  # 版本号迭代
    }
)

# --- 基础配置 ---
BASE_URL = "https://pighub.top"
ALL_IMAGES_API = f"{BASE_URL}/api/all-images"
HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
    "Referer": f"{BASE_URL}/"
}

_session: Optional[aiohttp.ClientSession] = None
driver = get_driver()

# --- 生命周期管理 ---
@driver.on_startup
async def _init_session():
    global _session
    if _session is None or _session.closed:
        _session = aiohttp.ClientSession(headers=HEADERS)
        logger.opt(colors=True).info("<g>[PigHub]</g> 全局 HTTP Session 已初始化")

@driver.on_shutdown
async def _close_session():
    global _session
    if _session:
        await _session.close()
        logger.opt(colors=True).info("<y>[PigHub]</y> 全局 HTTP Session 已关闭")

# --- 数据源层 (DataSource) ---
async def fetch_image_list() -> List[Dict[str, Any]]:
    """获取图片列表数据"""
    if _session is None or _session.closed:
        await _init_session()
    
    async with _session.get(ALL_IMAGES_API, timeout=10) as resp:
        resp.raise_for_status()
        data = await resp.json()
    return data.get("images", [])

async def download_image_bytes(url: str) -> bytes:
    """下载图片二进制数据"""
    logger.info(f"正在下载图片: {url}")
    async with _session.get(url, timeout=15) as resp:
        if resp.status != 200:
            raise ValueError(f"HTTP {resp.status}")
        img_bytes = await resp.read()
        if len(img_bytes) < 1024:
            raise ValueError("图片文件过小或不完整")
    return img_bytes

# --- 业务逻辑层 (Service) ---
async def send_pig_image(matcher, target: Dict[str, Any]):
    """
    统一的图片发送逻辑
    :param matcher: nonebot matcher 对象
    :param target: 选中的图片数据字典
    """
    try:
        pig_id = target.get("id", "???")
        title = target.get("title", "没名字的猪猪")
        
        # 构造图片链接
        raw_path = target.get("thumbnail") or f"/data/{target.get('filename')}"
        encoded_path = urllib.parse.quote(raw_path)
        img_url = f"{BASE_URL}{encoded_path}"

        # 下载并发送
        img_bytes = await download_image_bytes(img_url)
        
        msg = Message(f"No.{pig_id}【{title}】\n") + MessageSegment.image(img_bytes)
        await matcher.send(msg)
        
    except Exception as e:
        logger.error(f"发送失败: {str(e)}")
        await matcher.finish(f"猪猪出逃失败：{str(e)}")

# --- 指令层 (Controller) ---

# 1. 随机猪猪
get_pig = on_command("来张猪猪", aliases={"随机猪猪"}, priority=5, block=True)

@get_pig.handle()
async def handle_random_pig():
    try:
        images = await fetch_image_list()
        if not images:
            await get_pig.finish("猪猪仓库好像空了...")
        
        target = random.choice(images)
        await send_pig_image(get_pig, target)
        
    except Exception as e:
        logger.error(f"随机猪猪出错: {e}")
        await get_pig.finish("猪猪钻进泥潭里找不到了...")

# 2. 标签猪猪
def check_pig(event: MessageEvent) -> bool:
    msg = str(event.get_message()).strip()
    # 只要以猪猪结尾，且长度≥4就能触发 (例如 "来只粉色猪猪")
    return bool(re.search(r"来只(.+?)猪猪", msg))

get_pig_by_tag = on_command("来只", priority=15, block=True, rule=Rule(check_pig))

@get_pig_by_tag.handle()
async def handle_tag_pig(event: MessageEvent):
    try:
        msg = str(event.get_message()).strip()
        
        match = re.search(r"来只(.+?)猪猪", msg)
        if not match:
            logger.info("无法匹配到猪猪tag")
            return
        tag = match.group(1).strip()
        
        if not tag:
            await get_pig_by_tag.finish("猪猪的名字是空的哦~")

        images = await fetch_image_list()
        if not images:
            await get_pig_by_tag.finish("猪猪仓库好像空了...")

        # 模糊匹配
        match_list = [img for img in images if tag in img.get("title", "")]

        if not match_list:
            await get_pig_by_tag.finish(f"没有找到【{tag}】相关的猪猪哦~")

        match_list.sort(key=lambda x : len(x.get('title', '')))
        min_length = len(match_list[0].get("title", ""))
        shortest_matches = [img for img in match_list if len(img.get('title', '')) == min_length]

        target = random.choice(shortest_matches)
        await send_pig_image(get_pig_by_tag, target)

    except Exception as e:
        logger.error(f"标签猪猪出错: {e}")
        await get_pig_by_tag.finish("找猪猪的时候不小心掉进泥潭了...")
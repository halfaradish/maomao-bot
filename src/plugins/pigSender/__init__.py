import random
import aiohttp
from nonebot import on_command, get_driver
from nonebot.plugin import PluginMetadata
from nonebot.adapters.onebot.v11 import MessageSegment, Message
from nonebot.log import logger

__plugin_meta__ = PluginMetadata(
    name="PigSender",
    description="从 pighub.top 获取随机猪猪图片",
    usage="指令：来张猪猪 / 随机猪猪",
    config=None,
    extra={
        "author": "xqcherry",
        "version": "0.1.2"  # 修复了富媒体传输失败问题
    }
)

_cache = {"total": 1254}
API_URL = "https://pighub.top/api/images"
IMG_BASE_URL = "https://pighub.top/images"
HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
    "Referer": "https://pighub.top/"
}

_session: aiohttp.ClientSession = None
driver = get_driver()


@driver.on_startup
async def _init_session():
    global _session
    _session = aiohttp.ClientSession(headers=HEADERS)
    logger.opt(colors=True).info("<g>[PigHub]</g> 全局 HTTP Session 已创建")


@driver.on_shutdown
async def _close_session():
    global _session
    if _session:
        await _session.close()
        logger.opt(colors=True).info("<y>[PigHub]</y> 全局 HTTP Session 已关闭")


async def fetch_pig_data(limit: int = 1, offset: int = 0):
    """复用全局 Session 抓取数据"""
    if _session is None or _session.closed:
        await _init_session()

    params = {"limit": limit, "offset": offset, "sort": "latest"}
    async with _session.get(API_URL, params=params, timeout=10) as response:
        response.raise_for_status()
        return await response.json()


get_pig = on_command("来张猪猪", aliases={"随机猪猪"}, priority=5, block=True)


@get_pig.handle()
async def handle_pig():
    try:
        # 1. 动态同步 total
        init_data = await fetch_pig_data(limit=1, offset=0)
        try:
            current_total = int(init_data.get("total", _cache["total"]))
            _cache["total"] = current_total
        except (ValueError, TypeError):
            current_total = _cache["total"]

        # 2. 生成偏移量
        random_offset = random.randint(0, current_total - 1)

        # 3. 获取目标数据
        if random_offset == 0:
            target_data = init_data
        else:
            target_data = await fetch_pig_data(limit=1, offset=random_offset)

        # 4. 解析字段
        img_list = target_data.get("images") or target_data.get("data")
        if not img_list:
            await get_pig.finish("猪猪仓库好像空了...")

        img_item = img_list[0]
        filename = img_item.get("filename")
        title = img_item.get("title", "随机猪猪")

        if not filename:
            await get_pig.finish("获取图片信息失败...")

        # 5. 【核心修复】由 NoneBot 下载图片字节流
        img_url = f"{IMG_BASE_URL}/{filename}"
        
        async with _session.get(img_url, timeout=10) as img_resp:
            if img_resp.status != 200:
                logger.error(f"图片下载失败: HTTP {img_resp.status}")
                await get_pig.finish("猪猪被图床守卫拦住了...")
            
            img_bytes = await img_resp.read()

        # 发送二进制数据，NapCat 就不需要再去外网下载了
        await get_pig.send(
            Message(f"No.{random_offset} 【{title}】\n") +
            MessageSegment.image(img_bytes)
        )

    except Exception as e:
        logger.error(f"PigHub 插件运行出错: {str(e)}")
        await get_pig.finish("猪猪钻进泥潭里找不到了...")


logger.opt(colors=True).info("<g>[PigHub]</g> 随机猪猪插件注册成功！")
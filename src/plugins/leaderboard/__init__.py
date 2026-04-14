from nonebot import (
    on_command,
    logger,
    get_plugin_config
)
from nonebot.adapters.onebot.v11 import (
    GroupMessageEvent
)
from nonebot.params import CommandArg
from nonebot.plugin import PluginMetadata
from nonebot.adapters.onebot.v11 import Message

import aiohttp
import asyncio
import io

from .config import Config
from ..cmd_list.model import PluginGroupEnum

config = get_plugin_config(Config)

__plugin_meta__ = PluginMetadata(
    name="过题积分榜",
    description="查询洛谷过题积分排行榜",
    usage="过题积分榜 现役 —— 查询现役成员的过题积分\n过题积分榜 退役 —— 查询退役成员的过题积分\n过题积分榜 预备役 —— 查询预备役成员的过题积分",
    config=Config,
    type="application",
    supported_adapters={"~onebot.v11"},
    extra={
        "group": PluginGroupEnum.CONTEST.value,
        "badge_color": "yellow"
    }
)

leaderboard = on_command("过题积分榜", aliases={"积分榜"}, priority=10)

async def fetch_one(session: aiohttp.ClientSession, type: int):
    url: str = f"{config.qingluan_scores_data_base_url}?type={type}"
    try:
        async with session.get(url=url) as res:
            res.raise_for_status()
            data = await res.json()
            return [{"realName": item["realName"], "totalScore": item["totalScore"]} for item in data]
    except asyncio.TimeoutError as e:
        logger.error(f"请求超时，type:{type}")
        return []
    except aiohttp.ClientResponseError as e:
        logger.error(f"HTTP 错误: {e.status} - {e.message}")
        return []
    except aiohttp.ClientError as e:
        logger.error(f"网络层错误: {e}")
        return []

async def fetch_all(params: list):
    type_list: list = []
    for param in params:
        if param == "现役":
            type_list.append(1)
        elif param == "退役":
            type_list.append(2)
        elif param == "预备役":
            type_list.append(3)

    timeout_obj = aiohttp.ClientTimeout(total=config.timeout)
    async with aiohttp.ClientSession(timeout=timeout_obj) as session:
        tasks = [asyncio.create_task(fetch_one(session=session, type=t)) for _, t in enumerate(type_list)]
        results = await asyncio.gather(*tasks, return_exceptions=True)
    
    all_scores: list = []
    for result in results:
        if isinstance(result, Exception):
            logger.error(f"抓取失败：{result}")
        elif result is not None:
            all_scores.extend(result)
    
    return all_scores


# 导入图片生成模块
from .image_generator import generate_leaderboard_image

@leaderboard.handle()
async def handle_leaderboard(event: GroupMessageEvent, args: Message = CommandArg()):
    arg = args.extract_plain_text().strip()
    
    if not arg:
        await leaderboard.finish(config.help_msg)
    
    params = arg.split()

    records = await fetch_all(params=params)
    
    # 检查数据是否为空
    if not records:
        await leaderboard.finish("暂无积分数据")

    # 生成图片
    try:
        logger.info(f"开始生成积分榜图片，数据条数: {len(records)}")
        img_bytes = await generate_leaderboard_image(records, config)
        if img_bytes:
            logger.info(f"图片生成成功，大小: {len(img_bytes)} 字节")
            # 发送图片
            from nonebot.adapters.onebot.v11 import MessageSegment
            await leaderboard.finish(MessageSegment.image(img_bytes))
        else:
            logger.warning("图片生成失败，返回None")
    except Exception as e:
        # 如果出现异常，返回错误信息
        logger.error(f"生成图片失败: {e}")
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

from .config import Config

config = get_plugin_config(Config)

__plugin_meta__ = PluginMetadata(
    name="过题积分榜",
    description="查询洛谷过题积分排行榜",
    usage="过题积分榜 [预备役/老登]",
    type="application",
    supported_adapters={"~onebot.v11"},
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

def revers_to_rank_text_table(records: list):
    if not records:
        return "无过题积分榜数据"
    records.sort(key=lambda x: x["totalScore"], reverse=True)

    msg = "    Name    Score\n"
    for i, person in enumerate(records, 1):
        msg += f"{i:<3}{person['realName']:<6}{person['totalScore']}\n"

    return msg

@leaderboard.handle()
async def handle_leaderboard(event: GroupMessageEvent, args: Message = CommandArg()):
    arg = args.extract_plain_text().strip()
    
    if not arg:
        await leaderboard.finish(config.help_msg)
    
    params = arg.split()

    records = await fetch_all(params=params)

    msg = revers_to_rank_text_table(records=records)
    await leaderboard.finish(msg)
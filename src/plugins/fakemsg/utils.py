import datetime

from nonebot import logger, get_bot
from nonebot.adapters.onebot.v11 import Bot, Message
from typing import Optional, cast

from ...common.send_forward_msg import SenderInfo
from .config import config
from . import dao


MAX_DAILY_TIME = config.fakemsg_max_daily_time
bot_info: Optional["SenderInfo"] = None


async def get_daily_usage(user_id: str) -> int:
    """获取用户当日已使用次数"""
    return await dao.get_count(int(user_id), datetime.date.today())


async def daily_times_addone(user_id: str) -> None:
    """当日使用次数 +1（原子 upsert）"""
    await dao.incr(int(user_id), datetime.date.today())


async def get_bot_info() -> "SenderInfo":
    """获取机器人自身信息"""
    global bot_info
    if bot_info is None:
        bot: Bot = cast(Bot, get_bot())
        info = await bot.get_login_info()
        self_id = bot.self_id
        nickname = info['nickname']
        bot_info = SenderInfo(user_id=self_id, nickname=nickname, message=Message())
    return bot_info

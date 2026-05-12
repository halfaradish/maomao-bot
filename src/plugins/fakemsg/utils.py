from nonebot import logger, get_bot
from nonebot.adapters.onebot.v11 import Bot, Message
from typing import Optional, cast

from ...common.json_utils import JsonUtils
from ...common.send_forward_msg import SenderInfo
from .config import config


MAX_DAILY_TIME = config.fakemsg_max_daily_time
bot_info: Optional["SenderInfo"] = None


def get_plugin_config() -> tuple:
    data, _ = JsonUtils.read("fakemsg.json", {
        "person_users": [],
        "group_users": [],
        "daily_times_log": {}
    })
    if not isinstance(data, dict):
        logger.warning("无法正确读取文件，使用默认值")
        return [], [], {}
    return (
        data.get("person_users", []),
        data.get("group_users", []),
        data.get('daily_times_log', {})
    )


def daily_times_addone(user_id: str) -> dict:
    """增加使用次数并返回更新后的字典"""
    _, _, daily_times_log = get_plugin_config()
    current_times = daily_times_log.get(user_id, 0)
    current_times += 1
    daily_times_log[user_id] = current_times
    JsonUtils.update("fakemsg.json", updates={"daily_times_log": daily_times_log})
    return daily_times_log


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


def get_last_refresh_date() -> str:
    """获取上次刷新日期"""
    data, _ = JsonUtils.read("fakemsg.json", {})
    if not isinstance(data, dict):
        logger.warning("无法正确读取文件，使用默认值")
        return ""
    return data.get("last_refresh_date", "")


def set_last_refresh_date(date_str: str) -> bool:
    """设置上次刷新日期"""
    return JsonUtils.update("fakemsg.json", updates={"last_refresh_date": date_str})

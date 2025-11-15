from nonebot import (
    get_plugin_config,
    logger,
    on_command,
    require
)
from nonebot.adapters.onebot.v11 import (
    Bot,
    GroupMessageEvent,
    Message
)
from nonebot.rule import Rule
from nonebot.plugin import PluginMetadata
from nonebot.params import CommandArg
from nonebot.exception import FinishedException
require("nonebot_plugin_apscheduler")
import nonebot_plugin_apscheduler

from typing import List

from .config import Config
from .contest_fetcher import contest_fetcher, ContestInfo
from ...common.send_forward_msg import send_forword_msg

__plugin_meta__ = PluginMetadata(
    name="contest_reminder",
    description="",
    usage="",
    config=Config,
)

config = get_plugin_config(Config)

def is_get_contest_info_enable():
    logger.debug(f'get_contest_info_enable enable: {config.clist_gci_enable}')
    return config.clist_gci_enable

get_contest_info = on_command(
    cmd=config.clist_gci_cmd,
    rule=Rule(is_get_contest_info_enable),
    priority=config.clist_gci_priority,
    block=True
)

@get_contest_info.handle()
async def _(bot: Bot, event: GroupMessageEvent, args: Message = CommandArg()):
    # 获取天数
    raw_args: str = args.extract_plain_text().strip()
    # 获取偏移时间
    hours_ahead: int
    if raw_args and raw_args.isdigit():
        days = int(raw_args)
        hours_ahead = days * 24
        # 验证小时数是否在合理范围内
        max_hours = getattr(config, 'clist_max_hours_ahead', 720)
        if hours_ahead > max_hours:
            await get_contest_info.send(f"查询时间范围过大，请输入不超过{max_hours // 24}的数字")
            return
    else:
        return

    try:
        # 获取比赛信息
        contests: List[ContestInfo] = contest_fetcher.fetch_contests(platform_names=config.clist_platforms, hours_ahead=hours_ahead)

        # 如果没有比赛信息
        if not contests:
            get_contest_info.finish(f"{days} 天内无比赛")
        
        msg_list: List[str] = []
        msg_list.append(f"{days} 天内比赛信息\n适配平台{config.clist_platforms}")
        
        for contest in contests:
            msg_list.append(contest.to_string())

        await send_forword_msg.by_onebot_api(bot, event, msg_list, str(event.group_id))

    except FinishedException:
        pass
    except Exception as e:
        logger.error(f"获取比赛信息出错: {e}")

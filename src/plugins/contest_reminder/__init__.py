from nonebot import (
    get_plugin_config,
    logger,
    on_command,
    require
)
from nonebot.adapters.onebot.v11 import (
    Message
)
from nonebot.rule import Rule
from nonebot.plugin import PluginMetadata
from nonebot.params import CommandArg
require("nonebot_plugin_apscheduler")
import nonebot_plugin_apscheduler

from typing import List

from .config import Config
from .contest_fetcher import contest_fetcher, ContestInfo

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
async def _(args: Message = CommandArg()):
    raw_args: str = args.extract_plain_text().strip()
    # 获取偏移时间
    hours_ahead: int = config.clist_hours_ahead
    if raw_args == '':
        pass
    elif raw_args.isdigit():
        hours_ahead = int(raw_args)
        # 验证小时数是否在合理范围内
        max_hours = getattr(config, 'clist_max_hours_ahead', 720)
        if hours_ahead > max_hours:
            await get_contest_info.send(f"查询时间范围过大，请输入不超过{max_hours}小时的数字")
            return
    else:
        return

    # 获取比赛信息
    contests: List[ContestInfo] = contest_fetcher.fetch_contests(platform_names=config.clist_platforms)

    days: int = hours_ahead // 24
    hours: int = hours_ahead % 24
    msg: str = None
    if not contests:
        msg = f"{hours_ahead} 小时内无比赛"
    else:
        msg = f"{days} 天 {hours} 小时内比赛信息如下:\n\n"
        for contest in contests:
            msg += contest.to_string() + '\n\n'

    msg = msg.strip()
    logger.info(msg)
    await get_contest_info.send(msg)
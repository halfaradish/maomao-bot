from nonebot import (
    get_plugin_config,
    logger,
    on_command,
    require,
    get_bot,
)
from nonebot.adapters.onebot.v11 import (
    Bot,
    GroupMessageEvent,
    Message,
    MessageSegment
)
from nonebot.rule import Rule
from nonebot.plugin import PluginMetadata
from nonebot.params import CommandArg

require("nonebot_plugin_apscheduler")
from nonebot_plugin_apscheduler import scheduler

from typing import List, Dict, Optional
from uuid import uuid4
from datetime import datetime, timedelta

from .config import Config
from .contest_fetcher import contest_fetcher, ContestInfo
from ...common.send_forward_msg import send_forward_msg
from ...common import JsonUtils
from src.common.model.model import PluginGroupEnum, PluginBadgeColor


__plugin_meta__ = PluginMetadata(
    name="比赛提醒",
    description="比赛提醒插件，支持查询和定时提醒比赛信息",
    usage="/gci 天数 —— 查询指定天数内的比赛信息",
    config=Config,
    supported_adapters={"~onebot.v11"},
    extra={
        "group": PluginGroupEnum.CONTEST.value,
        "badge_color": PluginBadgeColor.YELLOW.value
    }
)

config = get_plugin_config(Config)


# ===========================
# 查询比赛命令
# ===========================
def is_get_contest_info_enable():
    return config.clist_gci_enable


get_contest_info = on_command(
    cmd=config.clist_gci_cmd,
    rule=Rule(is_get_contest_info_enable),
    priority=config.clist_gci_priority,
    block=True
)


@get_contest_info.handle()
async def _(bot: Bot, event: GroupMessageEvent, args: Message = CommandArg()):
    raw_args = args.extract_plain_text().strip()
    if not raw_args.isdigit():
        return

    days = int(raw_args)
    hours_ahead = days * 24
    max_hours = getattr(config, "clist_max_hours_ahead", 720)

    if hours_ahead > max_hours:
        await get_contest_info.finish(f"查询时间范围过大，请输入 ≤ {max_hours // 24}")

    contests: List[ContestInfo] = contest_fetcher.fetch_contests(
        platform_names=config.clist_platforms,
        hours_ahead=hours_ahead
    )

    if not contests:
        await get_contest_info.finish(f"{days} 天内无比赛")

    msg_list = [f"{days} 天内比赛信息\n平台：{config.clist_platforms}"]
    for contest in contests:
        msg_list.append(contest.to_string())

    await send_forward_msg.by_onebot_api(
        bot,
        event,
        msg_list,
        group_id=str(event.group_id)
    )


# ===========================
# 读取配置
# ===========================
def get_json_data() -> Dict:
    data, _ = JsonUtils.read(
        filename=config.clist_filename,
        default={"groups_send_by_plugin": []}
    )
    return data


# ===========================
# 比赛提醒发送（支持 fallback）
# ===========================
async def remind_contest_to_groups(
    contest: ContestInfo,
    fallback_group_id: Optional[int] = None
):
    bot: Bot = get_bot()
    data = get_json_data()
    group_ids: List[str] = data.get("groups_send_by_plugin", [])

    # fallback：用于 mock / 测试
    if not group_ids:
        if fallback_group_id:
            logger.warning(
                f"groups_send_by_plugin 为空，使用 fallback 群 {fallback_group_id}"
            )
            group_ids = [str(fallback_group_id)]
        else:
            logger.warning("groups_send_by_plugin 为空，未发送提醒")
            return

    for group_id in group_ids:
        message = Message([
            MessageSegment.at("all"),
            MessageSegment.text("\n"),
            MessageSegment.text(f"比赛提醒：\n{contest.to_string()}")
        ])
        await bot.send_group_msg(group_id=int(group_id), message=message)


# ===========================
# mock 测试命令（最终稳定版）
# ===========================
 


# ===========================
# 定时任务（正式用）
# ===========================
async def contest_reminder():
    contests: List[ContestInfo] = contest_fetcher.fetch_contests(
        platform_names=config.clist_platforms
    )

    for contest in contests:
        run_date = contest.start - timedelta(hours=1)
        scheduler.add_job(
            remind_contest_to_groups,
            "date",
            run_date=run_date,
            args=[contest],
            id=f"contest_reminder_{uuid4().hex}"
        )


if config.clist_schedule_job_enable:
    scheduler.add_job(
        contest_reminder,
        "cron",
        hour=config.clist_remind_run_time_hour,
        minute=0,
        second=0,
        id="contests_reminder"
    )



# @scheduler.scheduled_job(
#     "cron",
#     hour=config.clist_remind_run_time_hour,
#     minute=0,
#     second=0,
#     id="contests_reminder"
# )
# async def contest_reminder_scheduler():
#     """每日定时提醒"""
#     await contest_reminder()

# @scheduler.scheduled_job(
#     'date',
#     run_date=datetime.now() + timedelta(seconds=3),
#     id=f"contest_reminder_startup_{uuid4().hex[:8]}"
# )
# async def contest_reminder_startup():
#     """运行比赛提醒任务"""
#     logger.info("启动时开始执行赛程提醒任务")
#     # 直接执行一次比赛信息获取和提醒安排
#     await contest_reminder()
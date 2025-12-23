from nonebot import (
    get_plugin_config,
    logger,
    on_command,
    require,
    get_bot,
    get_driver
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
from nonebot_plugin_apscheduler import scheduler

from typing import List, Dict
from uuid import uuid4
from datetime import datetime, timedelta
import asyncio

from .config import Config
from .contest_fetcher import contest_fetcher, ContestInfo
from ...common.send_forward_msg import send_forword_msg
from ...common import JsonUtils
from nonebot.adapters.onebot.v11 import MessageSegment
from nonebot.adapters.onebot.v11 import MessageSegment as OBMessageSegment


def make_at_all_segment():
    """兼容不同 onebot 版本，返回用于艾特全体的 MessageSegment"""
    # 优先尝试标准方法
    if hasattr(OBMessageSegment, "at_all"):
        return OBMessageSegment.at_all()
    # 部分实现使用 at("all") 或 at(0) / at("all")
    if hasattr(OBMessageSegment, "at"):
        try:
            return OBMessageSegment.at("all")
        except Exception:
            try:
                return OBMessageSegment.at_all()  # 兜底再次尝试
            except Exception:
                pass
    # 最后退回到手动构造 CQ 码节点
    try:
        return OBMessageSegment("at", {"qq": "all"})
    except Exception:
        # 任何情况下返回空字符串，调用方需能接受
        return ""

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
async def _(bot: Bot, event: GroupMessageEvent, args: Message = CommandArg()) -> None:
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
        
        for idx, contest in enumerate(contests):
            if idx == 0:
                # 将艾特全体与首条比赛内容合并为同一消息节点
                at_seg = make_at_all_segment()
                msg_list.append([at_seg, f"比赛提醒：\n{contest.to_string()}"])
            else:
                msg_list.append(f"{contest.to_string()}")

        await send_forword_msg.by_onebot_api(bot, event, msg_list, str(event.group_id))

    except FinishedException:
        pass
    except Exception as e:
        logger.error(f"获取比赛信息出错: {e}")

def get_json_data() -> Dict:
    """读取json配置文件"""
    try:
        data, _ = JsonUtils.read(
            filename=config.clist_filename,
            default={
                "groups_send_by_plugin": []
            }
        )
        return data
    except Exception as e:
        logger.error(f"读取json文件时出错: {type(e).__name__}: {e}")
        # 返回默认值，确保程序可以继续运行
        return {
            "groups_send_by_plugin": []
        }

async def remind_contest_to_groups(contest: ContestInfo) -> None:
    """发送比赛提醒消息"""
    try:
        bot: Bot = get_bot()
        # 获取数据
        data: Dict = get_json_data()
        group_ids: List[str] = data.get('groups_send_by_plugin', [])
        
        if not group_ids:
            logger.debug("没有需要发送提醒的群组")
            return

        # 发送消息
        for group_id in group_ids:
            try:
                at_seg = make_at_all_segment()
                await bot.send_group_msg(
                    group_id=group_id,
                    message=Message([at_seg, "比赛提醒：\n" + f"{contest.to_string()}"])
                )
                logger.debug(f"成功向群组 {group_id} 发送比赛提醒")
            except Exception as e:
                logger.error(f"向群组 {group_id} 发送消息时出错: {e}")
                # 继续处理下一个群组，不中断整体流程
                continue
    except Exception as e:
        logger.error(f"发送消息时出错: {e}")
        return

async def contest_reminder():
    """安排比赛提醒"""
    # 获取比赛信息
    contests: List[ContestInfo] = contest_fetcher.fetch_contests(platform_names=config.clist_platforms)

    success_cnt = 0
    for contest in contests:
        run_date: datetime = contest.start - timedelta(hours=1)
        # 尝试安排提醒
        try:
            job_id=f"contest_reminder_{uuid4().hex[:8]}"
            scheduler.add_job(
                remind_contest_to_groups,
                'date',
                run_date=run_date,
                args=[contest],
                id=job_id
            )
            success_cnt += 1

        except Exception as e:
            logger.error(f"安排比赛提醒时出错: {e}")
            continue

    logger.info(f"成功安排 {success_cnt} 条比赛提醒")

# 根据enable状态-启动定时任务
if config.clist_schedule_job_enable:
    scheduler.add_job(
        contest_reminder,
        "cron",
        hour=config.clist_remind_run_time_hour,
        minute=0,
        second=0,
        id="contests_reminder"
    )
    scheduler.add_job(
        contest_reminder,
        'date',
        run_date=datetime.now() + timedelta(seconds=3),
        id=f"contest_reminder_startup_{uuid4().hex[:8]}"
    )
    logger.debug("已开启 contest_reminder 插件定时比赛提醒")
else:
    logger.debug("contest_reminder 插件定时比赛提醒已禁用")


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

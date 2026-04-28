from nonebot import logger
import datetime

from nonebot.plugin import require

from .config import config
from . import utils

require("nonebot_plugin_apscheduler")
from nonebot_plugin_apscheduler import scheduler

def refresh_daily_times_log() -> bool:
    """
    刷新daily_times_log，将所有用户的使用次数重置为0
    考虑数据一致性和并发安全问题
    """
    try:
        logger.info("[fakemsg] 开始执行每日额度刷新任务")

        today = datetime.date.today().strftime("%Y-%m-%d")

        from ...common.json_utils import JsonUtils
        success = JsonUtils.update("fakemsg.json", updates={"daily_times_log": {}, "last_refresh_date": today})

        if success:
            logger.info(f"[fakemsg] 每日额度刷新成功，日期: {today}")
        else:
            logger.error("[fakemsg] 每日额度刷新失败")

        return success
    except Exception as e:
        logger.error(f"[fakemsg] 每日额度刷新发生异常: {e}", exc_info=True)
        return False


def check_and_refresh_on_demand() -> bool:
    """
    按需检查并刷新daily_times_log
    用于防范24:00时bot掉线导致未更新的情况
    """
    try:
        today = datetime.date.today().strftime("%Y-%m-%d")
        last_refresh = utils.get_last_refresh_date()

        if last_refresh != today:
            logger.info(f"[fakemsg] 检测到日期变更，上次刷新日期: {last_refresh}，当前日期: {today}，需要执行刷新")
            return refresh_daily_times_log()
        return True
    except Exception as e:
        logger.error(f"[fakemsg] 按需检查刷新发生异常: {e}", exc_info=True)
        return False


if config.fakemsg_schedule_enable:
    @scheduler.scheduled_job(
        "cron",
        hour=config.fakemsg_schedule_hour,
        minute=config.fakemsg_schedule_minute,
        second=config.fakemsg_schedule_second,
        id="fakemsg_daily_refresh"
    )
    async def fakemsg_daily_refresh():
        """每日定时刷新额度"""
        refresh_daily_times_log()


def init_scheduler():
    """初始化调度器"""
    check_and_refresh_on_demand()

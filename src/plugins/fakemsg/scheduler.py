import datetime

from nonebot import logger

from nonebot.plugin import require

from .config import config
from . import dao

require("nonebot_plugin_apscheduler")
from nonebot_plugin_apscheduler import scheduler


async def cleanup_expired_usage() -> int:
    """清理历史日期的使用计数行

    计数按 usage_date 维度存储，天然按日期隔离，无需整体重置；
    当日之后的查询不受影响，只需定期清理旧行。
    """
    try:
        today = datetime.date.today()
        deleted = await dao.delete_before(today)
        logger.info(f"[fakemsg] 每日额度清理完成，删除 {deleted} 行历史计数")
        return deleted
    except Exception as e:
        logger.error(f"[fakemsg] 每日额度清理发生异常: {e}", exc_info=True)
        return 0


if config.fakemsg_schedule_enable:
    @scheduler.scheduled_job(
        "cron",
        hour=config.fakemsg_schedule_hour,
        minute=config.fakemsg_schedule_minute,
        second=config.fakemsg_schedule_second,
        id="fakemsg_daily_cleanup"
    )
    async def fakemsg_daily_cleanup():
        """每日定时清理历史额度计数"""
        await cleanup_expired_usage()

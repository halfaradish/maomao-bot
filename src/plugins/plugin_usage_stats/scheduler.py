"""插件使用统计 — 定期清理过期明细"""
from datetime import datetime, timedelta

from nonebot import logger
from nonebot_plugin_apscheduler import scheduler

from . import dao
from .config import plugin_config


@scheduler.scheduled_job("cron", hour=5, minute=0, id="plugin_usage_stats_cleanup")
async def cleanup_expired_records():
    days = plugin_config.plugin_usage_stats_retention_days
    before = datetime.now() - timedelta(days=days)
    deleted = await dao.delete_expired_records(before)
    if deleted:
        logger.info(f"[插件统计] 已清理 {before:%Y-%m-%d %H:%M} 前的过期明细 {deleted} 条")

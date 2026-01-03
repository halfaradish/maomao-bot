"""
Ack/Ann command plugin registration.
"""

# Import handlers on load
from . import plugin  # noqa: F401
from .config import Config
from .reminder_scheduler import get_scheduler

from nonebot import get_driver
from nonebot.log import logger

driver = get_driver()
plugin_config = Config.parse_obj(driver.config.dict())

# 启动提醒调度器（仅在插件启用时）
@driver.on_startup
async def startup():
    """插件启动时初始化提醒调度器"""
    if not plugin_config.enabled:
        logger.info("ack_manager 已禁用，提醒调度器不启动。")
        return
    scheduler = get_scheduler()
    await scheduler.start()


@driver.on_shutdown
async def shutdown():
    """插件关闭时停止提醒调度器"""
    if not plugin_config.enabled:
        return
    scheduler = get_scheduler()
    await scheduler.stop()



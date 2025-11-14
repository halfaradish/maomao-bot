"""
Ack/Ann command plugin registration.
"""

# Import handlers on load
from . import plugin  # noqa: F401
from .reminder_scheduler import get_scheduler

# 启动提醒调度器
from nonebot import get_driver

@get_driver().on_startup
async def startup():
    """插件启动时初始化提醒调度器"""
    scheduler = get_scheduler()
    await scheduler.start()

@get_driver().on_shutdown
async def shutdown():
    """插件关闭时停止提醒调度器"""
    scheduler = get_scheduler()
    await scheduler.stop()



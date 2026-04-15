"""
Ack/Ann command plugin registration.
"""

# Import handlers on load
from . import plugin  # noqa: F401
from .config import Config
from .reminder_scheduler import get_scheduler

from nonebot import get_driver
from nonebot.log import logger
from nonebot.plugin import PluginMetadata
from src.common.model.model import PluginGroupEnum, PluginBadgeColor

__plugin_meta__ = PluginMetadata(
    name="全员确认",
    description="群内确认和公告功能，支持表情回复追踪",
    usage="/ack 内容 —— 发起全群确认，要求表情回复\n/ack @QQ @分组 内容 —— 仅通知指定成员或数据库分组\n/ann 内容 —— 发布公告，不追踪表情\n/ack —— 查看帮助",
    config=Config,
    supported_adapters={"~onebot.v11"},
    extra={
        "group": PluginGroupEnum.GROUP_MANAGE.value,
        "badge_color": PluginBadgeColor.BLUE.value
    }
)

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



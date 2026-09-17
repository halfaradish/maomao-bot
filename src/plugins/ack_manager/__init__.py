"""
Ack/Ann command plugin registration.
"""

# Import handlers on load
from . import plugin  # noqa: F401
from .config import Config
from . import reminder_scheduler  # noqa: F401 — 导入即注册 apscheduler 提醒任务

from nonebot.plugin import PluginMetadata
from src.common.plugin_meta import PluginGroupEnum, PluginBadgeColor

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

# 提醒任务是 apscheduler 的 interval job（见 reminder_scheduler.register_job），
# 随 nonebot_plugin_apscheduler 的 start/shutdown 一起起停，本插件不再自管生命周期。



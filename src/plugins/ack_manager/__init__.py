"""
Ack/Ann command plugin registration.
"""

# Import handlers on load
from . import plugin  # noqa: F401
from .config import Config
from . import permissions  # noqa: F401 — 注册权限点到权限系统
from . import reminder_scheduler  # noqa: F401 — 导入即注册 apscheduler 提醒任务

from nonebot import get_driver
from nonebot.plugin import PluginMetadata
from src.common.permission import ensure_perm_group
from src.common.plugin_meta import PluginGroupEnum, PluginBadgeColor

#: 本插件的默认权限组名（成员由管理面板维护，不随重启变化）
DEFAULT_PERM_GROUP = "ack_manager_users"

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


@get_driver().on_startup
async def _ensure_default_perm_group():
    """确保本插件的默认权限组存在（幂等，不动已有成员）"""
    await ensure_perm_group(
        DEFAULT_PERM_GROUP,
        "ACK 公告管理",
        ["ack_manager:ack", "ack_manager:announce"],
        description="自动创建：全群确认与群公告的使用权限",
    )


# 提醒任务是 apscheduler 的 interval job（见 reminder_scheduler.register_job），
# 随 nonebot_plugin_apscheduler 的 start/shutdown 一起起停，本插件不再自管生命周期。



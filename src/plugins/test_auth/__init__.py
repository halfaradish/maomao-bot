"""权限系统测试插件（已弃用）

该插件曾用于测试司契（Siqi）权限系统，现已接入统一权限系统，
相关功能由 group_ban 插件提供，本插件不再需要。
"""
from nonebot.plugin import PluginMetadata

from src.common.model.model import PluginGroupEnum, PluginBadgeColor

__plugin_meta__ = PluginMetadata(
    name="权限系统测试（已弃用）",
    description="已弃用：司契权限系统测试插件，功能已由 group_ban 插件统一接管",
    usage="此插件已弃用，请使用 group_ban 插件提供的 ban/unban/kick 命令",
    supported_adapters={"~onebot.v11"},
    extra={
        "group": PluginGroupEnum.GROUP_MANAGE.value,
        "badge_color": PluginBadgeColor.BLUE.value
    }
)

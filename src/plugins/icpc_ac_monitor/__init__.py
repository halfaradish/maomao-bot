import os

from nonebot import get_plugin_config
from nonebot.plugin import PluginMetadata
from src.common.model.model import PluginGroupEnum, PluginBadgeColor

ICPC_AC_MONITOR_ENABLED = os.getenv("ICPC_AC_MONITOR_ENABLED", "true").lower() == "true"

if not ICPC_AC_MONITOR_ENABLED:
    __plugin_meta__ = PluginMetadata(
        name="AC监控（已禁用）",
        description="广西大学比赛 AC 监控插件（当前已禁用，设置 ICPC_AC_MONITOR_ENABLED=true 启用）",
        usage="此插件已在 .env 中禁用",
        supported_adapters={"~onebot.v11"},
        extra={
            "group": PluginGroupEnum.CONTEST.value,
            "badge_color": PluginBadgeColor.YELLOW.value
        }
    )
else:
    from .config import Config
    from .icpc_ac_monitor import start_monitor, stop_monitor

    __plugin_meta__ = PluginMetadata(
        name="AC监控",
        description="广西大学比赛 AC 监控插件",
        usage="开始监控 <url> —— 开始监控指定比赛的AC情况\n停止监控 —— 停止当前监控",
        config=Config,
        supported_adapters={"~onebot.v11"},
        extra={
            "group": PluginGroupEnum.CONTEST.value,
            "badge_color": PluginBadgeColor.YELLOW.value
        }
    )

    config = get_plugin_config(Config)


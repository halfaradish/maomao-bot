from nonebot import get_plugin_config
from nonebot.plugin import PluginMetadata
from src.common.plugin_guard import disabled_plugin_metadata, plugin_enabled
from src.common.plugin_meta import PluginGroupEnum, PluginBadgeColor

ICPC_AC_MONITOR_ENABLED = plugin_enabled("ICPC_AC_MONITOR_ENABLED")

if not ICPC_AC_MONITOR_ENABLED:
    __plugin_meta__ = disabled_plugin_metadata(
        "ICPC_AC_MONITOR_ENABLED",
        name="AC监控",
        description="广西大学比赛 AC 监控插件",
        group=PluginGroupEnum.CONTEST,
        badge_color=PluginBadgeColor.YELLOW,
    )
else:
    from .config import Config
    # handlers 注册全部命令 matcher；monitor_service 注册 on_startup 恢复钩子
    from . import handlers, monitor_service  # noqa: F401
    from .handlers import start_monitor, stop_monitor

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


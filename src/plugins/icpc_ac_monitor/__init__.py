from nonebot import get_plugin_config
from nonebot.plugin import PluginMetadata
# src/plugins/icpc_ac_monitor/__init__.py
from .icpc_ac_monitor import start_monitor, stop_monitor

from .config import Config
# src/plugins/icpc_ac_monitor/__init__.py

from nonebot.plugin import PluginMetadata

__plugin_meta__ = PluginMetadata(
    name="icpc_ac_monitor",      # ← 和目录名保持一致
    description="广西大学比赛 AC 监控",
    usage="开始监控 <url>  / 停止监控",
)


config = get_plugin_config(Config)


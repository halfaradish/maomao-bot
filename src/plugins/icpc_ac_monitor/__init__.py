from nonebot import get_plugin_config
from nonebot.plugin import PluginMetadata
from .icpc_ac_monitor import start_monitor, stop_monitor
from .config import Config
from ..cmd_list.model import PluginGroupEnum

__plugin_meta__ = PluginMetadata(
    name="AC监控",
    description="广西大学比赛 AC 监控插件",
    usage="开始监控 <url> —— 开始监控指定比赛的AC情况\n停止监控 —— 停止当前监控",
    config=Config,
    supported_adapters={"~onebot.v11"},
    extra={
        "group": PluginGroupEnum.CONTEST.value,
        "badge_color": "yellow"
    }
)


config = get_plugin_config(Config)


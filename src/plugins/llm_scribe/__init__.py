from nonebot.plugin import PluginMetadata
from .src import interfaces

__plugin_meta__ = PluginMetadata(
    name="智能总结",
    description="基于LLM的聊天记录智能总结插件",
    usage="",
    config="",
    extra={
        "group": "基础命令",
        "badge_color": "yellow"
    }
)
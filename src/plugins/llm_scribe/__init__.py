from nonebot.plugin import PluginMetadata
from .src import interfaces
from src.common.model.model import PluginGroupEnum, PluginBadgeColor

__plugin_meta__ = PluginMetadata(
    name="智能总结",
    description="基于LLM的聊天记录智能总结插件",
    usage="",
    config="",
    supported_adapters={"~onebot.v11"},
    extra={
        "group": PluginGroupEnum.UTILITY.value,
        "badge_color": PluginBadgeColor.YELLOW.value
    }
)
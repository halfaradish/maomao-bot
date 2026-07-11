import os

from nonebot.plugin import PluginMetadata
from src.common.model.model import PluginGroupEnum, PluginBadgeColor

# ── 插件启停开关 ──
LLM_SCRIBE_ENABLED = os.getenv("LLM_SCRIBE_ENABLED", "true").lower() == "true"

if not LLM_SCRIBE_ENABLED:
    __plugin_meta__ = PluginMetadata(
        name="智能总结（已禁用）",
        description="基于LLM的聊天记录智能总结插件（当前已禁用，设置 LLM_SCRIBE_ENABLED=true 启用）",
        usage="此插件已在环境变量中禁用",
        supported_adapters={"~onebot.v11"},
        extra={
            "group": PluginGroupEnum.UTILITY.value,
            "badge_color": PluginBadgeColor.YELLOW.value,
        },
    )
else:
    from .src import interfaces

    __plugin_meta__ = PluginMetadata(
        name="智能总结",
        description="基于LLM的聊天记录智能总结插件",
        usage="",
        config=None,
        supported_adapters={"~onebot.v11"},
        extra={
            "group": PluginGroupEnum.UTILITY.value,
            "badge_color": PluginBadgeColor.YELLOW.value,
        },
    )
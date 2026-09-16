from nonebot.plugin import PluginMetadata
from src.common.plugin_guard import disabled_plugin_metadata, plugin_enabled
from src.common.plugin_meta import PluginGroupEnum, PluginBadgeColor

# ── 插件启停开关 ──
LLM_SCRIBE_ENABLED = plugin_enabled("LLM_SCRIBE_ENABLED")

if not LLM_SCRIBE_ENABLED:
    __plugin_meta__ = disabled_plugin_metadata(
        "LLM_SCRIBE_ENABLED",
        name="智能总结",
        description="基于LLM的聊天记录智能总结插件",
        group=PluginGroupEnum.UTILITY,
        badge_color=PluginBadgeColor.YELLOW,
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
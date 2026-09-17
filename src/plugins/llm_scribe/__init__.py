from nonebot import get_driver
from nonebot.plugin import PluginMetadata
from src.common.plugin_guard import disabled_plugin_metadata, plugin_enabled
from src.common.plugin_meta import PluginGroupEnum, PluginBadgeColor

from . import permissions  # noqa: F401 — 注册权限点到权限系统

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

    @get_driver().on_startup
    async def _ensure_default_perm_group():
        """确保本插件的默认权限组存在（幂等，不动已有成员）"""
        from src.common.permission import ensure_perm_group

        await ensure_perm_group(
            "llm_scribe_users",
            "群聊摘要",
            ["llm_scribe:sum"],
            description="自动创建：生成群聊摘要的权限（消耗 LLM 额度）",
        )

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
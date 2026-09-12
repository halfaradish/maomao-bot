"""插件使用频率统计 — 明细记录各插件的真实使用情况

统计口径：run_preprocessor 全局钩子，handler 真正开始执行才计一次；
权限被拒、未匹配上的不计；仅统计消息事件（notice/request 不计）。

环境隔离：PLUGIN_USAGE_STATS_ENABLE 总开关（生产/测试共用数据库时建议
仅生产开启，关闭时完全不注册钩子与命令）；落库明细带 env_tag 环境标签，
查询默认只统计当前环境，即使误开也不会与另一环境的数据混淆。
"""
from nonebot import get_driver, logger
from nonebot.adapters import Bot, Event
from nonebot.adapters.onebot.v11 import GroupMessageEvent, MessageEvent
from nonebot.matcher import Matcher
from nonebot.message import run_preprocessor
from nonebot.plugin import PluginMetadata
from nonebot.typing import T_State

from src.common.database import Base, engine
from src.common.model.model import PluginBadgeColor, PluginGroupEnum

from . import dao
from .config import Config, excluded_plugins, plugin_config

__plugin_meta__ = PluginMetadata(
    name="插件使用统计",
    description="统计各插件使用频率，明细记录插件、触发人、来源群与触发时间",
    usage="插件统计 [今天|昨天|本周|本月|总] [全环境] [N] —— 查看插件使用榜单",
    config=Config,
    supported_adapters={"~onebot.v11"},
    extra={
        "group": PluginGroupEnum.UTILITY.value,
        "badge_color": PluginBadgeColor.GREEN.value,
        "author": "half",
        "version": "0.1.0",
    },
)

config = plugin_config
_excluded = excluded_plugins()

driver = get_driver()

if config.plugin_usage_stats_enable:

    @driver.on_startup
    async def _ensure_tables():
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)

    @run_preprocessor
    async def _record_plugin_usage(matcher: Matcher, bot: Bot, event: Event, state: T_State):
        plugin = matcher.plugin
        if plugin is None or not isinstance(event, MessageEvent):
            return
        module_name = plugin.module_name
        short_name = module_name.split(".")[-1]
        if short_name in _excluded or module_name in _excluded:
            return
        try:
            await dao.insert_usage_record(
                module_name=module_name,
                user_id=event.user_id,
                group_id=event.group_id if isinstance(event, GroupMessageEvent) else None,
            )
        except Exception as e:
            logger.warning(f"[插件统计] 记录使用数据失败（不影响消息处理）: {e}")

    from . import commands  # noqa: F401
    from . import scheduler  # noqa: F401

    logger.info(
        f"[插件统计] 已启用（环境: {dao.current_env_tag()}，排除: {sorted(_excluded)}）"
    )
else:
    logger.info("[插件统计] PLUGIN_USAGE_STATS_ENABLE=false，插件使用统计未启用")

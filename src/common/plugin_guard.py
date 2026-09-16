"""插件启停 guard：统一「导入期杀开关」的开关解析与「（已禁用）」存根元数据。

约定见 ``.claude/skills/nonebot-plugin-dev-guide/SKILL.md`` §9。典型用法：

.. code-block:: python

    MY_PLUGIN_ENABLED = plugin_enabled("MY_PLUGIN_ENABLED")

    if not MY_PLUGIN_ENABLED:
        __plugin_meta__ = disabled_plugin_metadata(
            "MY_PLUGIN_ENABLED",
            name="我的插件",
            description="功能描述",
            group=PluginGroupEnum.UTILITY,
            badge_color=PluginBadgeColor.GREEN,
        )
    else:
        __plugin_meta__ = PluginMetadata(...)
        from . import handlers  # noqa: F401

禁用分支只给存根元数据、不注册任何 handler —— NoneBot 加载器需要 ``__plugin_meta__``
存在，缺了会报 RuntimeError。
"""
import os

from nonebot import logger
from nonebot.plugin import PluginMetadata

from .plugin_meta import PluginBadgeColor, PluginGroupEnum

_TRUTHY = ("1", "true", "yes", "on")


def plugin_enabled(env_var: str, default: bool = True) -> bool:
    """读取插件启停开关。

    未设置或空串时返回 ``default``；比较大小写不敏感，``1`` / ``true`` / ``yes`` /
    ``on`` 视为开启，其余值（含 ``false`` / ``0`` / ``no`` / ``off``）视为关闭。
    """
    raw = os.getenv(env_var)
    if raw is None or not raw.strip():
        return default
    return raw.strip().lower() in _TRUTHY


def disabled_plugin_metadata(
    env_var: str,
    *,
    name: str,
    description: str,
    group: PluginGroupEnum,
    badge_color: PluginBadgeColor,
) -> PluginMetadata:
    """构造禁用存根元数据，并输出一条禁用日志。

    ``name`` 追加「（已禁用）」后缀，``description`` 传**插件原本的描述**、由这里补上
    启用方式。存根刻意**不带** ``config``，也不会注册任何 handler。
    """
    logger.info(f"[{env_var}] 插件已禁用，不注册任何 handler")
    return PluginMetadata(
        name=f"{name}（已禁用）",
        description=f"{description}（当前已禁用，设置 {env_var}=true 启用）",
        usage="此插件已在环境变量中禁用",
        supported_adapters={"~onebot.v11"},
        extra={"group": group.value, "badge_color": badge_color.value},
    )

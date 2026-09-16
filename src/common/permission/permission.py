"""
NoneBot Permission 适配器

将权限系统的 check_permission 包装为 nonebot.permission.Permission 实例，
可直接作为 on_command() 的 permission= 参数使用。
"""
from nonebot.adapters import Bot, Event
from nonebot.permission import Permission as NB_Permission

from src.common.permission.checker import check_permission


def permission_checker(perm_key: str) -> NB_Permission:
    """创建一个 NoneBot Permission 检查器（匹配器级放行）

    用法::

        from src.common.permission import ADMIN_PERM_KEY, permission_checker

        vv_blacklist_add = on_command(
            "vv拉黑",
            permission=permission_checker(ADMIN_PERM_KEY),
        )

    返回的 Permission 可与 NoneBot 内置权限通过 ``|`` 组合。

    注意 ``_check`` 的两个形参**必须带类型注解**：NoneBot 的 ``Dependent.parse``
    靠注解把形参解析成 ``BotParam`` / ``EventParam``，没有注解会在构造
    ``Permission`` 时直接抛 ``ValueError: Unknown parameter ...``。
    """
    async def _check(bot: Bot, event: Event) -> bool:
        return await check_permission(event, perm_key)

    return NB_Permission(_check)

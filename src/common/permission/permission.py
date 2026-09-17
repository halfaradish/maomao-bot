"""
NoneBot Permission 适配器

将权限系统的 check_permission 包装为 nonebot.permission.Permission 实例，
可直接作为 on_command() 的 permission= 参数使用。
"""
from nonebot.adapters import Bot, Event
from nonebot.log import logger
from nonebot.permission import Permission as NB_Permission

from src.common.permission.checker import check_permission, is_blacklisted


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


def blacklist_guard() -> NB_Permission:
    """创建一个「只挡黑名单」的 NoneBot Permission（默认放行）

    给**只读低风险**命令用：不声明权限点、不做默认拒绝，只拦黑名单里的用户/群，
    普通成员照常可用，管理员又能用黑名单统一限制个别人。需要按权限点授权、
    默认拒绝的场景请继续用 ``permission_checker``。

    用法::

        from src.common.permission import blacklist_guard

        today_files = on_command("今日文件", permission=blacklist_guard())

    与 ``permission_checker`` 的两点差异：

    * 查询黑名单要读库，失败时**放行**（fail-open）并记 warning —— 只读命令
      不该因为 DB 抖动对所有人生效为「不可用」；
    * ``_check`` 的形参同样**必须带类型注解**，原因见 ``permission_checker``。
    """
    async def _check(bot: Bot, event: Event) -> bool:
        try:
            user_id = int(getattr(event, "user_id"))
        except (AttributeError, TypeError, ValueError):
            # 取不到 user_id（非用户发起的事件）时不拦
            return True

        group_id = getattr(event, "group_id", None)
        try:
            return not await is_blacklisted(
                user_id, int(group_id) if group_id is not None else None
            )
        except Exception as exc:
            logger.opt(exception=True).warning(
                f"[permission] 黑名单查询失败，只读命令按放行处理: {exc}"
            )
            return True

    return NB_Permission(_check)

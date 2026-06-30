"""
NoneBot Permission 适配器

将权限系统的 check_permission 包装为 nonebot.permission.Permission 实例，
可直接作为 on_command() 的 permission= 参数使用。
"""
from nonebot.permission import Permission as NB_Permission

from src.common.permission.checker import check_permission


def permission_checker(perm_key: str) -> NB_Permission:
    """创建一个 NoneBot Permission 检查器

    用法:
        from nonebot.permission import SUPERUSER

        ban_cmd = on_command(
            "ban",
            permission=permission_checker("group_ban:ban") | SUPERUSER,
        )

    返回的 Permission 可与 SUPERUSER 等内置权限通过 | 组合。
    """
    async def _check(sender, event) -> bool:
        return await check_permission(event, perm_key)

    return NB_Permission(_check)

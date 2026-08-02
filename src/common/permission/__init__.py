"""
谛听权限系统 — 公共 API

提供三种接入方式：

1. Matcher 级权限（推荐）:
       from src.common.permission import permission_checker
       ban_cmd = on_command("ban", permission=permission_checker("group_ban:ban") | SUPERUSER)

2. 命令式 API（函数内联检查）:
       from src.common.permission import check_permission
       if not await check_permission(event, "group_ban:ban"):
           await matcher.finish("你没有权限")

3. 注册权限点（插件加载时声明）:
       from src.common.permission import register_perm_point
       register_perm_point("my_plugin:action", "功能名", "功能描述", plugin_name="my_plugin")
"""
from src.common.permission.registry import (
    perm_registry,
    register_perm_point,
    PermissionPointDef,
)
from src.common.permission.checker import (
    PermissionChecker,
    check_permission,
)
from src.common.permission.cache import perm_cache, TTLCache
from src.common.permission.supervisor import is_superuser
from src.common.permission.permission import permission_checker
from src.common.permission.queries import get_bound_group_ids

# 触发 startup hook 注册
from src.common.permission import auto_register  # noqa: F401

__all__ = [
    # 注册
    "perm_registry",
    "register_perm_point",
    "PermissionPointDef",
    # 校验
    "PermissionChecker",
    "check_permission",
    # NoneBot 适配
    "permission_checker",
    # 超级管理员
    "is_superuser",
    # 缓存（管理面板需要）
    "perm_cache",
    "TTLCache",
    # 查询
    "get_bound_group_ids",
]

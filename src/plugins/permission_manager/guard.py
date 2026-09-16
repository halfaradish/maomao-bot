"""本插件各子命令共用的辅助：权限缓存失效。

放行判断不再在这里 —— 管理员即「持有 ``ADMIN_PERM_KEY``」，直接调
``check_permission(event, ADMIN_PERM_KEY)`` 即可（见 ``dispatch.py`` / ``login.py``）。
之前那个先查 ``is_superuser`` 再查权限点的 ``_ensure_superuser`` 是冗余的：
``checker.check`` 的第 0 步本来就会为管理员短路放行。
"""
from typing import Optional

from nonebot import logger

from src.common.permission.cache import perm_cache


def _invalidate_related_cache(user_id: Optional[int] = None, group_id: Optional[int] = None):
    """失效相关缓存"""
    if user_id is not None:
        logger.debug(f"失效用户缓存: user_id={user_id}")
        perm_cache.clear_pattern(f"perm:{user_id}:")
    if group_id is not None:
        logger.debug(f"失效群缓存: group_id={group_id}")
        perm_cache.clear_pattern(f"perm::{group_id}:")
    # 全局失效兜底（权限组变更影响范围不可精确预测）
    if user_id is None and group_id is None:
        logger.debug("全局失效所有权限缓存")
        perm_cache.clear_all()

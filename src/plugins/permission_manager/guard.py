"""命令入口的两道横切关注点：放行判断与权限缓存失效。"""
from typing import Optional

from nonebot import logger
from nonebot.adapters.onebot.v11 import MessageEvent

from src.common.permission import check_permission
from src.common.permission.cache import perm_cache
from src.common.permission.supervisor import is_superuser


async def _ensure_superuser(event: MessageEvent) -> bool:
    """检查是否有权限管理权限系统"""
    if is_superuser(event.user_id):
        return True
    return await check_permission(event, "permission_manager:manage")


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

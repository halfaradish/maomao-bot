"""群级别的权限快速查询

auto_manage_group 的三个功能本质上是"群级别开关"——判断某个群是否开启了某功能，
而不是"用户有没有权限做某事"。因此这里提供比通用 check_permission()
更轻量的查询函数，跳过所有用户相关检查（用户黑/白名单、用户权限组成员等）。

检查链（2 步，vs check_permission 的 5 步）：
  1. 群白名单 → True（完全信任，不查权限组）
  2. GroupPermBinding → 绑定的权限组是否包含目标 perm_key
  3. 默认 → False
"""
from typing import Optional

from sqlalchemy import select

from src.common.database import async_session_factory
from src.common.permission.models import (
    GroupWhitelist,
    GroupPermBinding,
    PermissionGroupPerm,
    PermissionGroup,
)
from src.common.permission.cache import perm_cache


async def is_group_feature_enabled(group_id: int, perm_key: str) -> bool:
    """检查指定群是否开启了某个功能（群级别，不涉及用户）。

    比通用 check_permission() 更快：跳过用户黑名单/白名单/权限组成员检查，
    只做群白名单 + GroupPermBinding 两次 DB 查询。

    Args:
        group_id: QQ 群号
        perm_key: 权限点 key（如 "auto_manage_group:increase"）

    Returns:
        bool: 该群是否开启了此功能
    """
    cache_key = f"group_feature:{group_id}:{perm_key}"
    cached = perm_cache.get(cache_key)
    if cached is not None:
        return cached

    async with async_session_factory() as session:
        # 1. 群白名单 — 完全信任，直接放行
        stmt = select(GroupWhitelist.id).where(
            GroupWhitelist.group_id == group_id
        ).limit(1)
        if (await session.execute(stmt)).first() is not None:
            perm_cache.set(cache_key, True)
            return True

        # 2. GroupPermBinding → 绑定的权限组是否包含目标 perm_key
        stmt = (
            select(PermissionGroupPerm.id)
            .join(
                GroupPermBinding,
                GroupPermBinding.permission_group_id == PermissionGroupPerm.group_id,
            )
            .where(
                GroupPermBinding.qq_group_id == group_id,
                PermissionGroupPerm.perm_key == perm_key,
            )
            .limit(1)
        )
        result = (await session.execute(stmt)).first() is not None
        perm_cache.set(cache_key, result)
        return result


async def get_ban_word_log_targets() -> list[int]:
    """查询所有绑定了 auto_manage_group:ban_word_log_target 权限的群。

    这些群接收违禁词检测告警日志（合并转发消息）。
    这是一个全局查询——不按 source group 区分。

    Returns:
        list[int]: 应接收告警日志的所有 QQ 群号
    """
    cache_key = "ban_word_log_targets"
    cached = perm_cache.get(cache_key)
    if cached is not None:
        return cached

    async with async_session_factory() as session:
        stmt = (
            select(GroupPermBinding.qq_group_id)
            .join(
                PermissionGroup,
                GroupPermBinding.permission_group_id == PermissionGroup.id,
            )
            .join(
                PermissionGroupPerm,
                PermissionGroupPerm.group_id == PermissionGroup.id,
            )
            .where(
                PermissionGroupPerm.perm_key == "auto_manage_group:ban_word_log_target"
            )
            .distinct()
        )
        result = await session.execute(stmt)
        targets = [row[0] for row in result.all()]
        perm_cache.set(cache_key, targets)
        return targets

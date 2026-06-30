"""
权限校验引擎

实现完整的优先级校验流程：
  1. 超级管理员 → 直接放行
  2. 用户黑名单 → 拒绝
  3. 群黑名单 → 拒绝
  4. 群白名单 → 完全放行
  5. 用户白名单 → 完全放行
  6. 权限组成员 → 检查 perm_key
  7. 群绑定权限组 → 检查 perm_key
  8. 默认拒绝
"""
from typing import Optional

from nonebot.adapters.onebot.v11 import Event, GroupMessageEvent

from sqlalchemy import select

from src.common.database import async_session_factory
from src.common.permission.cache import perm_cache
from src.common.permission.models import (
    UserBlacklist,
    GroupBlacklist,
    UserWhitelist,
    GroupWhitelist,
    PermissionGroupMember,
    PermissionGroupPerm,
    GroupPermBinding,
)
from src.common.permission.supervisor import is_superuser


class PermissionChecker:
    """权限校验引擎"""

    async def check(self, event: Event, perm_key: str) -> bool:
        """检查事件发送者是否拥有指定权限（带缓存）"""
        user_id = event.user_id
        group_id: Optional[int] = None
        if hasattr(event, "group_id") and event.group_id is not None:
            group_id = event.group_id

        # 0. 超级管理员绕过所有检查（不缓存）
        if is_superuser(user_id):
            return True

        # 检查缓存
        cache_key = f"perm:{user_id}:{group_id}:{perm_key}"
        cached = perm_cache.get(cache_key)
        if cached is not None:
            return cached

        result = await self._check_internal(user_id, group_id, perm_key)
        perm_cache.set(cache_key, result)
        return result

    async def _check_internal(
        self,
        user_id: int,
        group_id: Optional[int],
        perm_key: str,
    ) -> bool:
        """无缓存的完整校验流程（单 session）"""
        async with async_session_factory() as session:
            # 1. 用户黑名单
            stmt = select(UserBlacklist.id).where(UserBlacklist.user_id == user_id).limit(1)
            if (await session.execute(stmt)).first() is not None:
                return False

            # 2. 群黑名单
            if group_id is not None:
                stmt = select(GroupBlacklist.id).where(GroupBlacklist.group_id == group_id).limit(1)
                if (await session.execute(stmt)).first() is not None:
                    return False

            # 3. 群白名单
            if group_id is not None:
                stmt = select(GroupWhitelist.id).where(GroupWhitelist.group_id == group_id).limit(1)
                if (await session.execute(stmt)).first() is not None:
                    return True

            # 4. 用户白名单
            stmt = select(UserWhitelist.id).where(UserWhitelist.user_id == user_id).limit(1)
            if (await session.execute(stmt)).first() is not None:
                return True

            # 5. 权限组检查
            return await self._check_permission_groups(session, user_id, group_id, perm_key)

    async def _check_permission_groups(
        self,
        session,
        user_id: int,
        group_id: Optional[int],
        perm_key: str,
    ) -> bool:
        """检查用户或其所在群是否通过权限组拥有目标权限"""
        pg_ids: set[int] = set()

        # a) 用户直接属于的权限组
        stmt = select(PermissionGroupMember.group_id).where(
            PermissionGroupMember.user_id == user_id
        )
        result = await session.execute(stmt)
        pg_ids.update(row[0] for row in result.all())

        # b) 用户所在群绑定的权限组
        if group_id is not None:
            stmt = select(GroupPermBinding.permission_group_id).where(
                GroupPermBinding.qq_group_id == group_id
            )
            result = await session.execute(stmt)
            pg_ids.update(row[0] for row in result.all())

        if not pg_ids:
            return False

        # c) 这些权限组中是否有任意一个拥有目标 perm_key
        stmt = select(PermissionGroupPerm.id).where(
            PermissionGroupPerm.group_id.in_(list(pg_ids)),
            PermissionGroupPerm.perm_key == perm_key,
        ).limit(1)
        result = await session.execute(stmt)
        return result.first() is not None


# 全局单例
permission_checker = PermissionChecker()


async def check_permission(event: Event, perm_key: str) -> bool:
    """便捷函数：检查事件发送者是否拥有指定权限"""
    return await permission_checker.check(event, perm_key)

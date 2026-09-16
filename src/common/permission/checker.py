"""
权限校验引擎

实现完整的优先级校验流程：
  0. 管理员（持有 ADMIN_PERM_KEY = ``permission_manager:manage``）→ 直接放行
  1. 用户黑名单 → 拒绝
  2. 群黑名单 → 拒绝
  3. 群白名单 → 完全放行
  4. 用户白名单 → 完全放行
  5. 权限组成员 → 检查 perm_key
  6. 群绑定权限组 → 检查 perm_key
  7. 默认拒绝

管理员判据来自权限系统自身（``perm_admin`` 权限组绑定 ADMIN_PERM_KEY），
而不是 NoneBot 的 SUPERUSERS 配置 —— 这样授予与撤销都在运行期生效，不必重启。
SUPERUSERS 只在启动播种时被读一次（见 ``bootstrap.py``）。
"""
from typing import Optional

from nonebot.adapters.onebot.v11 import Event

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

#: 管理员权限点 —— 持有它即绕过全部检查（等价于改造前的「超级管理员」）。
#: 由 ``perm_admin`` 权限组授予，该组及其初始成员在启动时播种。
ADMIN_PERM_KEY = "permission_manager:manage"


class PermissionChecker:
    """权限校验引擎"""

    async def check(self, event: Event, perm_key: str) -> bool:
        """检查事件发送者是否拥有指定权限（带缓存）"""
        user_id = event.user_id
        group_id: Optional[int] = None
        if hasattr(event, "group_id") and event.group_id is not None:
            group_id = event.group_id

        return await self.user_has_permission(user_id, perm_key, group_id)

    async def user_has_permission(
        self,
        user_id: int,
        perm_key: str,
        group_id: Optional[int] = None,
    ) -> bool:
        """按 user_id / group_id 判定权限（**不需要 onebot Event**，带缓存）

        没有事件对象可用的场景（REST API、WebUI 用户状态、启动播种）走这里；
        有事件对象的场景用 ``check(event, perm_key)``，它只是本函数的适配层。

        ``group_id`` 为 None 表示私聊语境：只统计用户的**直属**权限组成员关系，
        不算群绑定（群绑定天然只在那个群里生效）。
        """
        # 0. 管理员绕过所有检查（判据 = 持有 ADMIN_PERM_KEY）
        if await self._is_admin(user_id, group_id):
            return True

        # 检查缓存
        cache_key = f"perm:{user_id}:{group_id}:{perm_key}"
        cached = perm_cache.get(cache_key)
        if cached is not None:
            return cached

        result = await self._check_internal(user_id, group_id, perm_key)
        perm_cache.set(cache_key, result)
        return result

    async def _is_admin(self, user_id: int, group_id: Optional[int]) -> bool:
        """用户是否持有管理员权限点 ADMIN_PERM_KEY（= 管理员组 ``perm_admin`` 授予）

        直接调 ``_check_permission_groups`` 而不是 ``check``，因此不会递归。
        判定结果**会被缓存**（键刻意复用 ``perm:`` 前缀，好让管理操作里既有的
        ``clear_pattern("perm:{user_id}:")`` 能连带失效，撤权不必等满 TTL）。

        DB 查询失败不吞异常：与普通用户的检查一样向上抛（fail-closed ——
        拿不到权限组就绝不认为对方是管理员）。
        """
        cache_key = f"perm:{user_id}:{group_id}:{ADMIN_PERM_KEY}:bypass"
        cached = perm_cache.get(cache_key)
        if cached is not None:
            return cached

        async with async_session_factory() as session:
            result = await self._check_permission_groups(
                session, user_id, group_id, ADMIN_PERM_KEY
            )
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


async def user_has_permission(
    user_id: int,
    perm_key: str,
    group_id: Optional[int] = None,
) -> bool:
    """便捷函数：按 user_id 判定权限（**不需要 onebot Event**）

    用于没有事件对象的场景：REST API、WebUI、启动播种。
    """
    return await permission_checker.user_has_permission(user_id, perm_key, group_id)


async def is_blacklisted(user_id: int, group_id: Optional[int] = None) -> bool:
    """检查用户或其所在群是否命中黑名单

    黑名单在优先级链中高于白名单与权限组，因此 check_permission 对黑名单用户
    同样返回 False。需要把「被拒绝」与「无权限」区分开的场景（例如按群等级
    放行的业务兜底）用本函数单独判断。
    """
    async with async_session_factory() as session:
        stmt = select(UserBlacklist.id).where(UserBlacklist.user_id == user_id).limit(1)
        if (await session.execute(stmt)).first() is not None:
            return True

        if group_id is not None:
            stmt = select(GroupBlacklist.id).where(GroupBlacklist.group_id == group_id).limit(1)
            if (await session.execute(stmt)).first() is not None:
                return True

    return False

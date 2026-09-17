"""Aggregate user permission status endpoint."""
from fastapi import APIRouter, Request
from sqlalchemy import select
from sqlalchemy.orm import selectinload

from src.common.database import get_session
from src.common.permission.models import (
    PermissionGroup,
    PermissionGroupMember,
    UserBlacklist,
    UserWhitelist,
)
from src.common.permission import ADMIN_PERM_KEY, user_has_permission
from src.config.response import success

router = APIRouter()


@router.get("/users/{user_id}/status", summary="查看用户权限状态")
async def get_user_status(
    user_id: int,
    request: Request = None,
):
    """聚合查询指定用户的完整权限状态。

    返回：是否为管理员、黑名单/白名单状态、所属权限组（含权限点）、
    以及通过群绑定获得的权限组。
    """
    # 1. Admin check（持有管理员权限点；这里无群语境，只统计直属成员关系）
    #    放在会话块之前：user_has_permission 内部自带会话，留在块内会让
    #    单个请求同时持有 3 个连接。
    is_admin = await user_has_permission(user_id, ADMIN_PERM_KEY)

    async with get_session(commit=False) as session:
        # 2. Blacklist check
        bl = (await session.execute(
            select(UserBlacklist).where(UserBlacklist.user_id == user_id).limit(1)
        )).scalars().first()

        # 3. Whitelist check
        wl = (await session.execute(
            select(UserWhitelist).where(UserWhitelist.user_id == user_id).limit(1)
        )).scalars().first()

        # 4. Direct permission group memberships (with perms)
        member_rows = (await session.execute(
            select(PermissionGroupMember.group_id)
            .where(PermissionGroupMember.user_id == user_id)
        )).all()
        member_group_ids = [row[0] for row in member_rows]

        # 5. Resolve group details with perms
        permission_groups = []
        if member_group_ids:
            group_result = await session.execute(
                select(PermissionGroup)
                .where(PermissionGroup.id.in_(member_group_ids))
                .options(selectinload(PermissionGroup.permissions))
            )
            for g in group_result.scalars().all():
                permission_groups.append({
                    "id": g.id,
                    "name": g.name,
                    "display_name": g.display_name,
                    "description": g.description,
                    "perms": [p.perm_key for p in g.permissions],
                })

    return success(
        data={
            "user_id": user_id,
            "is_admin": is_admin,
            "blacklisted": {
                "reason": bl.reason,
                "created_by": bl.created_by,
                "created_at": bl.created_at.isoformat() if bl.created_at else None,
            } if bl else None,
            "whitelisted": {
                "reason": wl.reason,
                "created_by": wl.created_by,
                "created_at": wl.created_at.isoformat() if wl.created_at else None,
            } if wl else None,
            "permission_groups": permission_groups,
        },
        request=request,
    )

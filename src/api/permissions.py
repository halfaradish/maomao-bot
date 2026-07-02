"""
Permission management REST API for the WebUI management panel.

Provides full CRUD endpoints for all 8 permission tables, protected by JWT auth.
Serves as the API layer for Solution D (Swagger UI as management interface)
and is the foundation for future SPA phases.
"""
from fastapi import APIRouter, Depends, Query, Request
from pydantic import BaseModel, Field
from sqlalchemy import delete as sa_delete, func, select
from sqlalchemy.orm import selectinload

from src.common.database import async_session_factory
from src.common.permission.cache import perm_cache
from src.common.permission.models import (
    GroupBlacklist,
    GroupPermBinding,
    GroupWhitelist,
    PermissionGroup,
    PermissionGroupMember,
    PermissionGroupPerm,
    PermissionPoint,
    UserBlacklist,
    UserWhitelist,
)
from src.common.permission.supervisor import is_superuser
from src.config.response import success, error
from src.api.deps import TokenPayload, verify_token

# ---------------------------------------------------------------------------
# Router
# ---------------------------------------------------------------------------

router = APIRouter(prefix="/v1/permissions", tags=["权限管理"])


# ---------------------------------------------------------------------------
# Pydantic request schemas
# ---------------------------------------------------------------------------


class BlacklistUserAddRequest(BaseModel):
    """Add a user to the blacklist."""
    user_id: int = Field(..., description="QQ号")
    reason: str = Field("", description="拉黑原因")


class BlacklistGroupAddRequest(BaseModel):
    """Add a group to the blacklist."""
    group_id: int = Field(..., description="群号")
    reason: str = Field("", description="拉黑原因")


class WhitelistUserAddRequest(BaseModel):
    """Add a user to the whitelist."""
    user_id: int = Field(..., description="QQ号")
    reason: str = Field("", description="加白原因")


class WhitelistGroupAddRequest(BaseModel):
    """Add a group to the whitelist."""
    group_id: int = Field(..., description="群号")
    reason: str = Field("", description="加白原因")


class GroupCreateRequest(BaseModel):
    """Create a permission group (role)."""
    name: str = Field(..., min_length=1, max_length=100, description="权限组标识名（英文）")
    display_name: str = Field("", max_length=200, description="显示名称")
    description: str = Field("", description="描述")


class GroupMemberAddRequest(BaseModel):
    """Add members to a permission group."""
    user_ids: list[int] = Field(..., min_length=1, description="QQ号列表")


class GroupPermAddRequest(BaseModel):
    """Add permission keys to a permission group."""
    perm_keys: list[str] = Field(..., min_length=1, description="权限点key列表")


class BindingCreateRequest(BaseModel):
    """Bind a QQ group to a permission group."""
    qq_group_id: int = Field(..., description="QQ群号")
    permission_group_id: int = Field(..., description="权限组ID")


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


async def _paginate_query(session, stmt, page: int, page_size: int):
    """Apply pagination to a SELECT statement.

    Returns:
        tuple of (rows: list[Model], total: int)
    """
    count_stmt = select(func.count()).select_from(stmt.subquery())
    total = (await session.execute(count_stmt)).scalar() or 0

    offset = (page - 1) * page_size
    stmt = stmt.offset(offset).limit(page_size)
    result = await session.execute(stmt)
    rows = list(result.scalars().all())

    return rows, total


def _get_caller(auth: TokenPayload) -> int:
    """Extract the QQ number from JWT payload as int."""
    return int(auth.payload["sub"])


def _build_page_data(items: list, total: int, page: int, page_size: int) -> dict:
    """Build standardized paginated response data."""
    return {"items": items, "total": total, "page": page, "page_size": page_size}


# ---------------------------------------------------------------------------
# Blacklist — Users
# ---------------------------------------------------------------------------


@router.get("/blacklist/users", summary="列出用户黑名单")
async def list_blacklist_users(
    page: int = Query(1, ge=1, description="页码"),
    size: int = Query(20, ge=1, le=100, description="每页数量"),
    auth: TokenPayload = Depends(verify_token),
    request: Request = None,
):
    """分页列出所有被拉黑的用户，按创建时间倒序。"""
    async with async_session_factory() as session:
        stmt = select(UserBlacklist).order_by(UserBlacklist.created_at.desc())
        rows, total = await _paginate_query(session, stmt, page, size)

    items = [_serialize_blacklist_user(r) for r in rows]
    return success(data=_build_page_data(items, total, page, size), request=request)


@router.post("/blacklist/users", summary="添加用户到黑名单")
async def add_blacklist_user(
    body: BlacklistUserAddRequest,
    auth: TokenPayload = Depends(verify_token),
    request: Request = None,
):
    """将一个用户加入黑名单。已存在则返回提示。"""
    created_by = _get_caller(auth)
    async with async_session_factory() as session:
        existing = (await session.execute(
            select(UserBlacklist.id).where(UserBlacklist.user_id == body.user_id).limit(1)
        )).first()
        if existing:
            return success(
                message=f"用户 {body.user_id} 已在黑名单中",
                data={"user_id": body.user_id},
                request=request,
            )
        session.add(UserBlacklist(
            user_id=body.user_id,
            reason=body.reason,
            created_by=created_by,
        ))
        await session.commit()

    perm_cache.clear_pattern(f"perm:{body.user_id}:")
    return success(
        message=f"已将用户 {body.user_id} 加入黑名单",
        data={"user_id": body.user_id, "reason": body.reason, "created_by": created_by},
        request=request,
    )


@router.delete("/blacklist/users/{user_id}", summary="从黑名单移除用户")
async def remove_blacklist_user(
    user_id: int,
    auth: TokenPayload = Depends(verify_token),
    request: Request = None,
):
    """从黑名单中移除指定用户。"""
    async with async_session_factory() as session:
        result = await session.execute(
            sa_delete(UserBlacklist).where(UserBlacklist.user_id == user_id)
        )
        await session.commit()
        if result.rowcount == 0:
            return success(
                message=f"用户 {user_id} 不在黑名单中",
                data={"user_id": user_id},
                request=request,
            )

    perm_cache.clear_pattern(f"perm:{user_id}:")
    return success(
        message=f"已将用户 {user_id} 从黑名单移除",
        data={"user_id": user_id},
        request=request,
    )


# ---------------------------------------------------------------------------
# Blacklist — Groups
# ---------------------------------------------------------------------------


@router.get("/blacklist/groups", summary="列出群黑名单")
async def list_blacklist_groups(
    page: int = Query(1, ge=1, description="页码"),
    size: int = Query(20, ge=1, le=100, description="每页数量"),
    auth: TokenPayload = Depends(verify_token),
    request: Request = None,
):
    """分页列出所有被拉黑的群，按创建时间倒序。"""
    async with async_session_factory() as session:
        stmt = select(GroupBlacklist).order_by(GroupBlacklist.created_at.desc())
        rows, total = await _paginate_query(session, stmt, page, size)

    items = [_serialize_blacklist_group(r) for r in rows]
    return success(data=_build_page_data(items, total, page, size), request=request)


@router.post("/blacklist/groups", summary="添加群到黑名单")
async def add_blacklist_group(
    body: BlacklistGroupAddRequest,
    auth: TokenPayload = Depends(verify_token),
    request: Request = None,
):
    """将一个群加入黑名单。已存在则返回提示。"""
    created_by = _get_caller(auth)
    async with async_session_factory() as session:
        existing = (await session.execute(
            select(GroupBlacklist.id).where(GroupBlacklist.group_id == body.group_id).limit(1)
        )).first()
        if existing:
            return success(
                message=f"群 {body.group_id} 已在黑名单中",
                data={"group_id": body.group_id},
                request=request,
            )
        session.add(GroupBlacklist(
            group_id=body.group_id,
            reason=body.reason,
            created_by=created_by,
        ))
        await session.commit()

    perm_cache.clear_pattern(f"perm::{body.group_id}:")
    return success(
        message=f"已将群 {body.group_id} 加入黑名单",
        data={"group_id": body.group_id, "reason": body.reason, "created_by": created_by},
        request=request,
    )


@router.delete("/blacklist/groups/{group_id}", summary="从黑名单移除群")
async def remove_blacklist_group(
    group_id: int,
    auth: TokenPayload = Depends(verify_token),
    request: Request = None,
):
    """从黑名单中移除指定群。"""
    async with async_session_factory() as session:
        result = await session.execute(
            sa_delete(GroupBlacklist).where(GroupBlacklist.group_id == group_id)
        )
        await session.commit()
        if result.rowcount == 0:
            return success(
                message=f"群 {group_id} 不在黑名单中",
                data={"group_id": group_id},
                request=request,
            )

    perm_cache.clear_pattern(f"perm::{group_id}:")
    return success(
        message=f"已将群 {group_id} 从黑名单移除",
        data={"group_id": group_id},
        request=request,
    )


# ---------------------------------------------------------------------------
# Whitelist — Users
# ---------------------------------------------------------------------------


@router.get("/whitelist/users", summary="列出用户白名单")
async def list_whitelist_users(
    page: int = Query(1, ge=1, description="页码"),
    size: int = Query(20, ge=1, le=100, description="每页数量"),
    auth: TokenPayload = Depends(verify_token),
    request: Request = None,
):
    """分页列出所有白名单用户，按创建时间倒序。"""
    async with async_session_factory() as session:
        stmt = select(UserWhitelist).order_by(UserWhitelist.created_at.desc())
        rows, total = await _paginate_query(session, stmt, page, size)

    items = [_serialize_whitelist_user(r) for r in rows]
    return success(data=_build_page_data(items, total, page, size), request=request)


@router.post("/whitelist/users", summary="添加用户到白名单")
async def add_whitelist_user(
    body: WhitelistUserAddRequest,
    auth: TokenPayload = Depends(verify_token),
    request: Request = None,
):
    """将一个用户加入白名单。已存在则返回提示。"""
    created_by = _get_caller(auth)
    async with async_session_factory() as session:
        existing = (await session.execute(
            select(UserWhitelist.id).where(UserWhitelist.user_id == body.user_id).limit(1)
        )).first()
        if existing:
            return success(
                message=f"用户 {body.user_id} 已在白名单中",
                data={"user_id": body.user_id},
                request=request,
            )
        session.add(UserWhitelist(
            user_id=body.user_id,
            reason=body.reason,
            created_by=created_by,
        ))
        await session.commit()

    perm_cache.clear_pattern(f"perm:{body.user_id}:")
    return success(
        message=f"已将用户 {body.user_id} 加入白名单",
        data={"user_id": body.user_id, "reason": body.reason, "created_by": created_by},
        request=request,
    )


@router.delete("/whitelist/users/{user_id}", summary="从白名单移除用户")
async def remove_whitelist_user(
    user_id: int,
    auth: TokenPayload = Depends(verify_token),
    request: Request = None,
):
    """从白名单中移除指定用户。"""
    async with async_session_factory() as session:
        result = await session.execute(
            sa_delete(UserWhitelist).where(UserWhitelist.user_id == user_id)
        )
        await session.commit()
        if result.rowcount == 0:
            return success(
                message=f"用户 {user_id} 不在白名单中",
                data={"user_id": user_id},
                request=request,
            )

    perm_cache.clear_pattern(f"perm:{user_id}:")
    return success(
        message=f"已将用户 {user_id} 从白名单移除",
        data={"user_id": user_id},
        request=request,
    )


# ---------------------------------------------------------------------------
# Whitelist — Groups
# ---------------------------------------------------------------------------


@router.get("/whitelist/groups", summary="列出群白名单")
async def list_whitelist_groups(
    page: int = Query(1, ge=1, description="页码"),
    size: int = Query(20, ge=1, le=100, description="每页数量"),
    auth: TokenPayload = Depends(verify_token),
    request: Request = None,
):
    """分页列出所有白名单群，按创建时间倒序。"""
    async with async_session_factory() as session:
        stmt = select(GroupWhitelist).order_by(GroupWhitelist.created_at.desc())
        rows, total = await _paginate_query(session, stmt, page, size)

    items = [_serialize_whitelist_group(r) for r in rows]
    return success(data=_build_page_data(items, total, page, size), request=request)


@router.post("/whitelist/groups", summary="添加群到白名单")
async def add_whitelist_group(
    body: WhitelistGroupAddRequest,
    auth: TokenPayload = Depends(verify_token),
    request: Request = None,
):
    """将一个群加入白名单。已存在则返回提示。"""
    created_by = _get_caller(auth)
    async with async_session_factory() as session:
        existing = (await session.execute(
            select(GroupWhitelist.id).where(GroupWhitelist.group_id == body.group_id).limit(1)
        )).first()
        if existing:
            return success(
                message=f"群 {body.group_id} 已在白名单中",
                data={"group_id": body.group_id},
                request=request,
            )
        session.add(GroupWhitelist(
            group_id=body.group_id,
            reason=body.reason,
            created_by=created_by,
        ))
        await session.commit()

    perm_cache.clear_pattern(f"perm::{body.group_id}:")
    return success(
        message=f"已将群 {body.group_id} 加入白名单",
        data={"group_id": body.group_id, "reason": body.reason, "created_by": created_by},
        request=request,
    )


@router.delete("/whitelist/groups/{group_id}", summary="从白名单移除群")
async def remove_whitelist_group(
    group_id: int,
    auth: TokenPayload = Depends(verify_token),
    request: Request = None,
):
    """从白名单中移除指定群。"""
    async with async_session_factory() as session:
        result = await session.execute(
            sa_delete(GroupWhitelist).where(GroupWhitelist.group_id == group_id)
        )
        await session.commit()
        if result.rowcount == 0:
            return success(
                message=f"群 {group_id} 不在白名单中",
                data={"group_id": group_id},
                request=request,
            )

    perm_cache.clear_pattern(f"perm::{group_id}:")
    return success(
        message=f"已将群 {group_id} 从白名单移除",
        data={"group_id": group_id},
        request=request,
    )


# ---------------------------------------------------------------------------
# Permission Groups — CRUD
# ---------------------------------------------------------------------------


@router.get("/groups", summary="列出权限组")
async def list_permission_groups(
    page: int = Query(1, ge=1, description="页码"),
    size: int = Query(20, ge=1, le=100, description="每页数量"),
    auth: TokenPayload = Depends(verify_token),
    request: Request = None,
):
    """分页列出所有权限组，按名称排序。"""
    async with async_session_factory() as session:
        stmt = select(PermissionGroup).order_by(PermissionGroup.name)
        rows, total = await _paginate_query(session, stmt, page, size)

    items = [_serialize_permission_group(r) for r in rows]
    return success(data=_build_page_data(items, total, page, size), request=request)


@router.post("/groups", summary="创建权限组")
async def create_permission_group(
    body: GroupCreateRequest,
    auth: TokenPayload = Depends(verify_token),
    request: Request = None,
):
    """创建一个新的权限组（角色）。name 为唯一标识符。"""
    created_by = _get_caller(auth)
    async with async_session_factory() as session:
        existing = (await session.execute(
            select(PermissionGroup.id).where(PermissionGroup.name == body.name).limit(1)
        )).first()
        if existing:
            return success(
                message=f"权限组 {body.name} 已存在",
                data={"name": body.name},
                request=request,
            )
        group = PermissionGroup(
            name=body.name,
            display_name=body.display_name,
            description=body.description,
            created_by=created_by,
        )
        session.add(group)
        await session.commit()
        group_id = group.id

    perm_cache.clear_all()
    return success(
        message=f"已创建权限组 {body.name}",
        data={
            "id": group_id,
            "name": body.name,
            "display_name": body.display_name,
            "description": body.description,
            "created_by": created_by,
        },
        request=request,
    )


@router.get("/groups/{group_id}", summary="查看权限组详情")
async def get_permission_group(
    group_id: int,
    auth: TokenPayload = Depends(verify_token),
    request: Request = None,
):
    """查看权限组详情，包含成员列表和权限点列表。"""
    async with async_session_factory() as session:
        result = await session.execute(
            select(PermissionGroup)
            .where(PermissionGroup.id == group_id)
            .options(
                selectinload(PermissionGroup.members),
                selectinload(PermissionGroup.permissions),
            )
        )
        group = result.scalars().first()
        if group is None:
            return success(
                message=f"权限组 ID={group_id} 不存在",
                request=request,
            )

        return success(
            data={
                "id": group.id,
                "name": group.name,
                "display_name": group.display_name,
                "description": group.description,
                "created_by": group.created_by,
                "created_at": group.created_at.isoformat() if group.created_at else None,
                "updated_at": group.updated_at.isoformat() if group.updated_at else None,
                "members": [
                    {"id": m.id, "user_id": m.user_id, "created_at": m.created_at.isoformat() if m.created_at else None}
                    for m in group.members
                ],
                "permissions": [
                    {"id": p.id, "perm_key": p.perm_key, "created_at": p.created_at.isoformat() if p.created_at else None}
                    for p in group.permissions
                ],
            },
            request=request,
        )


@router.delete("/groups/{group_id}", summary="删除权限组")
async def delete_permission_group(
    group_id: int,
    auth: TokenPayload = Depends(verify_token),
    request: Request = None,
):
    """删除权限组（级联删除其成员和权限点关联）。"""
    async with async_session_factory() as session:
        result = await session.execute(
            sa_delete(PermissionGroup).where(PermissionGroup.id == group_id)
        )
        await session.commit()
        if result.rowcount == 0:
            return success(
                message=f"权限组 ID={group_id} 不存在",
                request=request,
            )

    perm_cache.clear_all()
    return success(
        message=f"已删除权限组 ID={group_id}",
        data={"id": group_id},
        request=request,
    )


# ---------------------------------------------------------------------------
# Permission Groups — Members
# ---------------------------------------------------------------------------


@router.get("/groups/{group_id}/members", summary="列出权限组成员")
async def list_group_members(
    group_id: int,
    auth: TokenPayload = Depends(verify_token),
    request: Request = None,
):
    """列出指定权限组的所有成员。"""
    async with async_session_factory() as session:
        # Verify group exists
        group = (await session.execute(
            select(PermissionGroup.id).where(PermissionGroup.id == group_id).limit(1)
        )).first()
        if group is None:
            return success(message=f"权限组 ID={group_id} 不存在", request=request)

        result = await session.execute(
            select(PermissionGroupMember)
            .where(PermissionGroupMember.group_id == group_id)
            .order_by(PermissionGroupMember.user_id)
        )
        members = result.scalars().all()

    items = [
        {"id": m.id, "user_id": m.user_id, "created_at": m.created_at.isoformat() if m.created_at else None}
        for m in members
    ]
    return success(data={"group_id": group_id, "members": items, "total": len(items)}, request=request)


@router.post("/groups/{group_id}/members", summary="添加权限组成员（批量）")
async def add_group_members(
    group_id: int,
    body: GroupMemberAddRequest,
    auth: TokenPayload = Depends(verify_token),
    request: Request = None,
):
    """批量添加用户到权限组。已存在的成员会被跳过并记录。"""
    async with async_session_factory() as session:
        # Verify group exists
        group = (await session.execute(
            select(PermissionGroup.id).where(PermissionGroup.id == group_id).limit(1)
        )).first()
        if group is None:
            return success(message=f"权限组 ID={group_id} 不存在", request=request)

        added: list[int] = []
        skipped: list[int] = []
        for user_id in body.user_ids:
            existing = (await session.execute(
                select(PermissionGroupMember.id).where(
                    PermissionGroupMember.group_id == group_id,
                    PermissionGroupMember.user_id == user_id,
                ).limit(1)
            )).first()
            if existing:
                skipped.append(user_id)
            else:
                session.add(PermissionGroupMember(group_id=group_id, user_id=user_id))
                added.append(user_id)

        if added:
            await session.commit()

    if added:
        perm_cache.clear_all()
    return success(
        message=f"已添加 {len(added)} 个成员" + (f"，跳过 {len(skipped)} 个已存在" if skipped else ""),
        data={"group_id": group_id, "added": added, "skipped": skipped},
        request=request,
    )


@router.delete("/groups/{group_id}/members/{user_id}", summary="移除权限组成员")
async def remove_group_member(
    group_id: int,
    user_id: int,
    auth: TokenPayload = Depends(verify_token),
    request: Request = None,
):
    """从权限组中移除指定用户。"""
    async with async_session_factory() as session:
        result = await session.execute(
            sa_delete(PermissionGroupMember).where(
                PermissionGroupMember.group_id == group_id,
                PermissionGroupMember.user_id == user_id,
            )
        )
        await session.commit()
        if result.rowcount == 0:
            return success(
                message=f"用户 {user_id} 不在权限组 ID={group_id} 中",
                data={"group_id": group_id, "user_id": user_id},
                request=request,
            )

    perm_cache.clear_all()
    return success(
        message=f"已将用户 {user_id} 从权限组 ID={group_id} 移除",
        data={"group_id": group_id, "user_id": user_id},
        request=request,
    )


# ---------------------------------------------------------------------------
# Permission Groups — Permissions
# ---------------------------------------------------------------------------


@router.get("/groups/{group_id}/perms", summary="列出权限组的权限点")
async def list_group_perms(
    group_id: int,
    auth: TokenPayload = Depends(verify_token),
    request: Request = None,
):
    """列出指定权限组绑定的所有权限点。"""
    async with async_session_factory() as session:
        group = (await session.execute(
            select(PermissionGroup.id).where(PermissionGroup.id == group_id).limit(1)
        )).first()
        if group is None:
            return success(message=f"权限组 ID={group_id} 不存在", request=request)

        result = await session.execute(
            select(PermissionGroupPerm)
            .where(PermissionGroupPerm.group_id == group_id)
            .order_by(PermissionGroupPerm.perm_key)
        )
        perms = result.scalars().all()

    items = [
        {"id": p.id, "perm_key": p.perm_key, "created_at": p.created_at.isoformat() if p.created_at else None}
        for p in perms
    ]
    return success(data={"group_id": group_id, "permissions": items, "total": len(items)}, request=request)


@router.post("/groups/{group_id}/perms", summary="添加权限组的权限点（批量）")
async def add_group_perms(
    group_id: int,
    body: GroupPermAddRequest,
    auth: TokenPayload = Depends(verify_token),
    request: Request = None,
):
    """批量添加权限点到权限组。已存在的权限点会被跳过并记录。"""
    async with async_session_factory() as session:
        group = (await session.execute(
            select(PermissionGroup.id).where(PermissionGroup.id == group_id).limit(1)
        )).first()
        if group is None:
            return success(message=f"权限组 ID={group_id} 不存在", request=request)

        added: list[str] = []
        skipped: list[str] = []
        for perm_key in body.perm_keys:
            existing = (await session.execute(
                select(PermissionGroupPerm.id).where(
                    PermissionGroupPerm.group_id == group_id,
                    PermissionGroupPerm.perm_key == perm_key,
                ).limit(1)
            )).first()
            if existing:
                skipped.append(perm_key)
            else:
                session.add(PermissionGroupPerm(group_id=group_id, perm_key=perm_key))
                added.append(perm_key)

        if added:
            await session.commit()

    if added:
        perm_cache.clear_all()
    return success(
        message=f"已添加 {len(added)} 个权限点" + (f"，跳过 {len(skipped)} 个已存在" if skipped else ""),
        data={"group_id": group_id, "added": added, "skipped": skipped},
        request=request,
    )


@router.delete("/groups/{group_id}/perms/{perm_key:path}", summary="移除权限组的权限点")
async def remove_group_perm(
    group_id: int,
    perm_key: str,
    auth: TokenPayload = Depends(verify_token),
    request: Request = None,
):
    """从权限组中移除指定权限点。

    perm_key 可以是完整路径（如 `plugin_name:action`），
    包含冒号时会被正确解析。
    """
    async with async_session_factory() as session:
        result = await session.execute(
            sa_delete(PermissionGroupPerm).where(
                PermissionGroupPerm.group_id == group_id,
                PermissionGroupPerm.perm_key == perm_key,
            )
        )
        await session.commit()
        if result.rowcount == 0:
            return success(
                message=f"权限点 {perm_key} 不在权限组 ID={group_id} 中",
                data={"group_id": group_id, "perm_key": perm_key},
                request=request,
            )

    perm_cache.clear_all()
    return success(
        message=f"已将权限点 {perm_key} 从权限组 ID={group_id} 移除",
        data={"group_id": group_id, "perm_key": perm_key},
        request=request,
    )


# ---------------------------------------------------------------------------
# Group-Permission Bindings
# ---------------------------------------------------------------------------


@router.get("/bindings", summary="列出群-权限组绑定")
async def list_bindings(
    group_id: int = Query(None, description="按QQ群号过滤"),
    auth: TokenPayload = Depends(verify_token),
    request: Request = None,
):
    """列出所有群与权限组的绑定关系，可按群号过滤。"""
    async with async_session_factory() as session:
        if group_id is not None:
            stmt = select(GroupPermBinding).where(
                GroupPermBinding.qq_group_id == group_id
            ).order_by(GroupPermBinding.qq_group_id)
        else:
            stmt = select(GroupPermBinding).order_by(
                GroupPermBinding.qq_group_id, GroupPermBinding.permission_group_id
            )
        rows = list((await session.execute(stmt)).scalars().all())

    items = [_serialize_binding(r) for r in rows]
    return success(
        data={"items": items, "total": len(items)},
        request=request,
    )


@router.post("/bindings", summary="创建群-权限组绑定")
async def create_binding(
    body: BindingCreateRequest,
    auth: TokenPayload = Depends(verify_token),
    request: Request = None,
):
    """将一个QQ群绑定到权限组，群成员将获得该组的权限。"""
    async with async_session_factory() as session:
        # Verify permission group exists
        pg = (await session.execute(
            select(PermissionGroup.id, PermissionGroup.name)
            .where(PermissionGroup.id == body.permission_group_id)
            .limit(1)
        )).first()
        if pg is None:
            return success(
                message=f"权限组 ID={body.permission_group_id} 不存在",
                request=request,
            )

        # Check duplicate
        existing = (await session.execute(
            select(GroupPermBinding.id).where(
                GroupPermBinding.qq_group_id == body.qq_group_id,
                GroupPermBinding.permission_group_id == body.permission_group_id,
            ).limit(1)
        )).first()
        if existing:
            return success(
                message=f"群 {body.qq_group_id} 已绑定权限组 ID={body.permission_group_id}",
                data={"qq_group_id": body.qq_group_id, "permission_group_id": body.permission_group_id},
                request=request,
            )

        binding = GroupPermBinding(
            qq_group_id=body.qq_group_id,
            permission_group_id=body.permission_group_id,
        )
        session.add(binding)
        await session.commit()
        binding_id = binding.id

    perm_cache.clear_all()
    return success(
        message=f"已将群 {body.qq_group_id} 绑定到权限组 ID={body.permission_group_id}（名称: {pg[1]}）",
        data={
            "id": binding_id,
            "qq_group_id": body.qq_group_id,
            "permission_group_id": body.permission_group_id,
            "permission_group_name": pg[1],
        },
        request=request,
    )


@router.delete("/bindings/{binding_id}", summary="删除群-权限组绑定")
async def delete_binding(
    binding_id: int,
    auth: TokenPayload = Depends(verify_token),
    request: Request = None,
):
    """解除指定绑定（按绑定ID）。"""
    async with async_session_factory() as session:
        # Fetch binding info before deletion
        binding = (await session.execute(
            select(GroupPermBinding).where(GroupPermBinding.id == binding_id).limit(1)
        )).scalars().first()
        if binding is None:
            return success(
                message=f"绑定 ID={binding_id} 不存在",
                request=request,
            )

        qq_group_id = binding.qq_group_id
        await session.execute(
            sa_delete(GroupPermBinding).where(GroupPermBinding.id == binding_id)
        )
        await session.commit()

    perm_cache.clear_all()
    return success(
        message=f"已解除群 {qq_group_id} 的绑定 ID={binding_id}",
        data={"id": binding_id, "qq_group_id": qq_group_id},
        request=request,
    )


# ---------------------------------------------------------------------------
# Permission Points (read-only)
# ---------------------------------------------------------------------------


@router.get("/points", summary="列出权限点")
async def list_permission_points(
    plugin: str = Query(None, description="按插件名过滤"),
    page: int = Query(1, ge=1, description="页码"),
    size: int = Query(20, ge=1, le=100, description="每页数量"),
    auth: TokenPayload = Depends(verify_token),
    request: Request = None,
):
    """列出所有已注册的权限点，支持按插件名过滤。权限点为只读（由插件自动注册）。"""
    async with async_session_factory() as session:
        if plugin:
            stmt = select(PermissionPoint).where(
                PermissionPoint.plugin_name == plugin
            ).order_by(PermissionPoint.plugin_name, PermissionPoint.perm_key)
        else:
            stmt = select(PermissionPoint).order_by(
                PermissionPoint.plugin_name, PermissionPoint.perm_key
            )
        rows, total = await _paginate_query(session, stmt, page, size)

    items = [
        {
            "id": p.id,
            "plugin_name": p.plugin_name,
            "perm_key": p.perm_key,
            "name": p.name,
            "description": p.description,
        }
        for p in rows
    ]
    return success(data=_build_page_data(items, total, page, size), request=request)


# ---------------------------------------------------------------------------
# User Status (aggregate lookup)
# ---------------------------------------------------------------------------


@router.get("/users/{user_id}/status", summary="查看用户权限状态")
async def get_user_status(
    user_id: int,
    auth: TokenPayload = Depends(verify_token),
    request: Request = None,
):
    """聚合查询指定用户的完整权限状态。

    返回：是否为超管、黑名单/白名单状态、所属权限组（含权限点）、
    以及通过群绑定获得的权限组。
    """
    async with async_session_factory() as session:
        # 1. Superuser check
        superuser = is_superuser(user_id)

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
            "is_superuser": superuser,
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


# ---------------------------------------------------------------------------
# Cache Management
# ---------------------------------------------------------------------------


@router.post("/cache/clear", summary="清除权限缓存")
async def clear_permission_cache(
    auth: TokenPayload = Depends(verify_token),
    request: Request = None,
):
    """清除所有权限检查缓存。权限变更后通常自动失效，此端点用于手动强制刷新。"""
    perm_cache.clear_all()
    return success(message="权限缓存已清除", request=request)


# ---------------------------------------------------------------------------
# Serialization helpers
# ---------------------------------------------------------------------------


def _serialize_blacklist_user(r: UserBlacklist) -> dict:
    return {
        "id": r.id,
        "user_id": r.user_id,
        "reason": r.reason,
        "created_by": r.created_by,
        "created_at": r.created_at.isoformat() if r.created_at else None,
        "updated_at": r.updated_at.isoformat() if r.updated_at else None,
    }


def _serialize_blacklist_group(r: GroupBlacklist) -> dict:
    return {
        "id": r.id,
        "group_id": r.group_id,
        "reason": r.reason,
        "created_by": r.created_by,
        "created_at": r.created_at.isoformat() if r.created_at else None,
        "updated_at": r.updated_at.isoformat() if r.updated_at else None,
    }


def _serialize_whitelist_user(r: UserWhitelist) -> dict:
    return {
        "id": r.id,
        "user_id": r.user_id,
        "reason": r.reason,
        "created_by": r.created_by,
        "created_at": r.created_at.isoformat() if r.created_at else None,
        "updated_at": r.updated_at.isoformat() if r.updated_at else None,
    }


def _serialize_whitelist_group(r: GroupWhitelist) -> dict:
    return {
        "id": r.id,
        "group_id": r.group_id,
        "reason": r.reason,
        "created_by": r.created_by,
        "created_at": r.created_at.isoformat() if r.created_at else None,
        "updated_at": r.updated_at.isoformat() if r.updated_at else None,
    }


def _serialize_permission_group(r: PermissionGroup) -> dict:
    return {
        "id": r.id,
        "name": r.name,
        "display_name": r.display_name,
        "description": r.description,
        "created_by": r.created_by,
        "created_at": r.created_at.isoformat() if r.created_at else None,
        "updated_at": r.updated_at.isoformat() if r.updated_at else None,
    }


def _serialize_binding(r: GroupPermBinding) -> dict:
    return {
        "id": r.id,
        "qq_group_id": r.qq_group_id,
        "permission_group_id": r.permission_group_id,
        "created_at": r.created_at.isoformat() if r.created_at else None,
    }

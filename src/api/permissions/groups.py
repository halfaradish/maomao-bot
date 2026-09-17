"""Permission group endpoints — CRUD, members, and permission points."""
from fastapi import APIRouter, Depends, Request
from sqlalchemy import delete as sa_delete, select
from sqlalchemy.orm import selectinload

from src.api.deps import TokenPayload, verify_token
from src.common.database import get_session
from src.common.permission.cache import perm_cache
from src.common.permission.models import (
    PermissionGroup,
    PermissionGroupMember,
    PermissionGroupPerm,
)
from src.config.response import success

from .helpers import (
    PageParams,
    _build_page_data,
    _get_caller,
    _paginate_query,
    _serialize_permission_group,
)
from .schemas import GroupCreateRequest, GroupMemberAddRequest, GroupPermAddRequest

router = APIRouter()


# ---------------------------------------------------------------------------
# Permission Groups — CRUD
# ---------------------------------------------------------------------------


@router.get("/groups", summary="列出权限组")
async def list_permission_groups(
    page_params: PageParams = Depends(PageParams),
    request: Request = None,
):
    """分页列出所有权限组，按名称排序。"""
    async with get_session(commit=False) as session:
        stmt = select(PermissionGroup).order_by(PermissionGroup.name)
        rows, total = await _paginate_query(session, stmt, page_params.page, page_params.size)

    items = [_serialize_permission_group(r) for r in rows]
    return success(data=_build_page_data(items, total, page_params.page, page_params.size), request=request)


@router.post("/groups", summary="创建权限组")
async def create_permission_group(
    body: GroupCreateRequest,
    auth: TokenPayload = Depends(verify_token),
    request: Request = None,
):
    """创建一个新的权限组（角色）。name 为唯一标识符。"""
    created_by = _get_caller(auth)
    async with get_session() as session:
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
        await session.flush()
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
    request: Request = None,
):
    """查看权限组详情，包含成员列表和权限点列表。"""
    async with get_session(commit=False) as session:
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
    request: Request = None,
):
    """删除权限组（级联删除其成员和权限点关联）。"""
    async with get_session() as session:
        result = await session.execute(
            sa_delete(PermissionGroup).where(PermissionGroup.id == group_id)
        )
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
    request: Request = None,
):
    """列出指定权限组的所有成员。"""
    async with get_session(commit=False) as session:
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
    request: Request = None,
):
    """批量添加用户到权限组。已存在的成员会被跳过并记录。"""
    async with get_session() as session:
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
    request: Request = None,
):
    """从权限组中移除指定用户。"""
    async with get_session() as session:
        result = await session.execute(
            sa_delete(PermissionGroupMember).where(
                PermissionGroupMember.group_id == group_id,
                PermissionGroupMember.user_id == user_id,
            )
        )
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
    request: Request = None,
):
    """列出指定权限组绑定的所有权限点。"""
    async with get_session(commit=False) as session:
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
    request: Request = None,
):
    """批量添加权限点到权限组。已存在的权限点会被跳过并记录。"""
    async with get_session() as session:
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
    request: Request = None,
):
    """从权限组中移除指定权限点。

    perm_key 可以是完整路径（如 `plugin_name:action`），
    包含冒号时会被正确解析。
    """
    async with get_session() as session:
        result = await session.execute(
            sa_delete(PermissionGroupPerm).where(
                PermissionGroupPerm.group_id == group_id,
                PermissionGroupPerm.perm_key == perm_key,
            )
        )
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

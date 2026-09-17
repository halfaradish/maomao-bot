"""Group-to-permission-group binding endpoints."""
from fastapi import APIRouter, Query, Request
from sqlalchemy import delete as sa_delete, select

from src.common.database import get_session
from src.common.permission.cache import perm_cache
from src.common.permission.models import GroupPermBinding, PermissionGroup
from src.config.response import success

from .helpers import _serialize_binding
from .schemas import BindingCreateRequest

router = APIRouter()


@router.get("/groups/{group_id}/bindings", summary="列出权限组已绑定的QQ群")
async def list_group_bindings(
    group_id: int,
    request: Request = None,
):
    """列出指定权限组已绑定的所有QQ群。"""
    async with get_session(commit=False) as session:
        group = (await session.execute(
            select(PermissionGroup.id).where(PermissionGroup.id == group_id).limit(1)
        )).first()
        if group is None:
            return success(message=f"权限组 ID={group_id} 不存在", request=request)

        result = await session.execute(
            select(GroupPermBinding)
            .where(GroupPermBinding.permission_group_id == group_id)
            .order_by(GroupPermBinding.qq_group_id)
        )
        bindings = result.scalars().all()

    items = [_serialize_binding(b) for b in bindings]
    return success(data={"group_id": group_id, "bindings": items, "total": len(items)}, request=request)


@router.get("/bindings", summary="列出群-权限组绑定")
async def list_bindings(
    group_id: int = Query(None, description="按QQ群号过滤"),
    request: Request = None,
):
    """列出所有群与权限组的绑定关系，可按群号过滤。"""
    async with get_session(commit=False) as session:
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
    request: Request = None,
):
    """将一个QQ群绑定到权限组，群成员将获得该组的权限。"""
    async with get_session() as session:
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
        await session.flush()
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
    request: Request = None,
):
    """解除指定绑定（按绑定ID）。"""
    async with get_session() as session:
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

    perm_cache.clear_all()
    return success(
        message=f"已解除群 {qq_group_id} 的绑定 ID={binding_id}",
        data={"id": binding_id, "qq_group_id": qq_group_id},
        request=request,
    )

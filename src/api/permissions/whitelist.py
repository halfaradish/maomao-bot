"""Whitelist endpoints — users and groups."""
from fastapi import APIRouter, Depends, Request
from sqlalchemy import delete as sa_delete, select

from src.api.deps import TokenPayload, verify_token
from src.common.database import async_session_factory
from src.common.permission.cache import perm_cache
from src.common.permission.models import GroupWhitelist, UserWhitelist
from src.config.response import success

from .helpers import (
    PageParams,
    _build_page_data,
    _get_caller,
    _paginate_query,
    _serialize_whitelist_group,
    _serialize_whitelist_user,
)
from .schemas import WhitelistGroupAddRequest, WhitelistUserAddRequest

router = APIRouter()


# ---------------------------------------------------------------------------
# Whitelist — Users
# ---------------------------------------------------------------------------


@router.get("/whitelist/users", summary="列出用户白名单")
async def list_whitelist_users(
    page_params: PageParams = Depends(PageParams),
    request: Request = None,
):
    """分页列出所有白名单用户，按创建时间倒序。"""
    async with async_session_factory() as session:
        stmt = select(UserWhitelist).order_by(UserWhitelist.created_at.desc())
        rows, total = await _paginate_query(session, stmt, page_params.page, page_params.size)

    items = [_serialize_whitelist_user(r) for r in rows]
    return success(data=_build_page_data(items, total, page_params.page, page_params.size), request=request)


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
    page_params: PageParams = Depends(PageParams),
    request: Request = None,
):
    """分页列出所有白名单群，按创建时间倒序。"""
    async with async_session_factory() as session:
        stmt = select(GroupWhitelist).order_by(GroupWhitelist.created_at.desc())
        rows, total = await _paginate_query(session, stmt, page_params.page, page_params.size)

    items = [_serialize_whitelist_group(r) for r in rows]
    return success(data=_build_page_data(items, total, page_params.page, page_params.size), request=request)


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

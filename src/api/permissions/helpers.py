"""Shared helpers for the permission management REST API.

Package-private: pagination, caller identity, response shaping, and row
serialization used across the resource sub-routers.
"""
from fastapi import Query
from sqlalchemy import func, select

from src.api.deps import TokenPayload
from src.common.permission.models import (
    GroupBlacklist,
    GroupPermBinding,
    GroupWhitelist,
    PermissionGroup,
    UserBlacklist,
    UserWhitelist,
)


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


class PageParams:
    """分页查询参数，供列表端点作为依赖注入（page/size 保留原有约束与描述）。"""

    def __init__(
        self,
        page: int = Query(1, ge=1, description="页码"),
        size: int = Query(20, ge=1, le=100, description="每页数量"),
    ):
        self.page = page
        self.size = size


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

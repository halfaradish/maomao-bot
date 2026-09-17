"""Permission point endpoints (read-only)."""
from fastapi import APIRouter, Depends, Query, Request
from sqlalchemy import select

from src.common.database import get_session
from src.common.permission.models import PermissionPoint
from src.config.response import success

from .helpers import PageParams, _build_page_data, _paginate_query

router = APIRouter()


@router.get("/points/plugins", summary="列出所有插件名")
async def list_permission_plugins(
    request: Request = None,
):
    """列出所有已注册权限点的插件名（去重）。"""
    async with get_session(commit=False) as session:
        stmt = select(PermissionPoint.plugin_name).distinct().order_by(PermissionPoint.plugin_name)
        result = await session.execute(stmt)
        plugins = [row[0] for row in result.all()]

    return success(data={"plugins": plugins}, request=request)


@router.get("/points", summary="列出权限点")
async def list_permission_points(
    plugin: str = Query(None, description="按插件名过滤"),
    page_params: PageParams = Depends(PageParams),
    request: Request = None,
):
    """列出所有已注册的权限点，支持按插件名过滤。权限点为只读（由插件自动注册）。"""
    async with get_session(commit=False) as session:
        if plugin:
            stmt = select(PermissionPoint).where(
                PermissionPoint.plugin_name == plugin
            ).order_by(PermissionPoint.plugin_name, PermissionPoint.perm_key)
        else:
            stmt = select(PermissionPoint).order_by(
                PermissionPoint.plugin_name, PermissionPoint.perm_key
            )
        rows, total = await _paginate_query(session, stmt, page_params.page, page_params.size)

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
    return success(data=_build_page_data(items, total, page_params.page, page_params.size), request=request)

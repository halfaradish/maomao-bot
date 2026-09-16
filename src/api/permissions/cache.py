"""Permission cache maintenance endpoint."""
from fastapi import APIRouter, Request

from src.common.permission.cache import perm_cache
from src.config.response import success

router = APIRouter()


@router.post("/cache/clear", summary="清除权限缓存")
async def clear_permission_cache(
    request: Request = None,
):
    """清除所有权限检查缓存。权限变更后通常自动失效，此端点用于手动强制刷新。"""
    perm_cache.clear_all()
    return success(message="权限缓存已清除", request=request)

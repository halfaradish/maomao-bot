"""
Permission management REST API for the WebUI management panel.

Provides full CRUD endpoints for all 8 permission tables, protected by JWT auth.
Serves as the API layer for Solution D (Swagger UI as management interface)
and is the foundation for future SPA phases.

Sub-routers are included in the original decorator order so the resulting
route table (and therefore OpenAPI path order) is unchanged.
"""
from fastapi import APIRouter, Depends

from src.api.deps import verify_token

from . import bindings, blacklist, cache, groups, points, status, whitelist

router = APIRouter(
    prefix="/v1/permissions",
    tags=["权限管理"],
    dependencies=[Depends(verify_token)],
)

router.include_router(blacklist.router)
router.include_router(whitelist.router)
router.include_router(groups.router)
router.include_router(bindings.router)
router.include_router(points.router)
router.include_router(status.router)
router.include_router(cache.router)

__all__ = ["router"]

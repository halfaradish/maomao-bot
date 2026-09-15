"""
插件元信息 API — 为 WebUI 插件管理页提供只读数据。

数据来源：NoneBot 的 get_loaded_plugins()（与 QQ 群内 /help 菜单同源），
权限点数量从 permission_points 表按插件名聚合。
"""
from fastapi import APIRouter, Depends, Request
from nonebot import get_loaded_plugins
from sqlalchemy import func, select

from src.api.deps import TokenPayload, verify_token
from src.common.database import async_session_factory
from src.common.permission.models import PermissionPoint
from src.config.response import success

router = APIRouter()


@router.get('/plugins', summary="列出所有插件")
async def list_plugins(
    auth: TokenPayload = Depends(verify_token),
    request: Request = None,
):
    """列出所有已加载插件（含外部插件），按 group + name 排序。纯展示数据。"""
    # 权限点数量聚合：plugin_name -> count
    perm_counts: dict[str, int] = {}
    async with async_session_factory() as session:
        stmt = (
            select(PermissionPoint.plugin_name, func.count(PermissionPoint.id))
            .group_by(PermissionPoint.plugin_name)
        )
        result = await session.execute(stmt)
        perm_counts = {name: count for name, count in result.all()}

    items = []
    for plugin in get_loaded_plugins():
        metadata = plugin.metadata
        if metadata is None:
            continue
        module_name = plugin.module_name

        # 权限点数量：先按 module_name 精确匹配，再按最后一段（插件目录名）匹配
        perm_count = perm_counts.get(module_name)
        if perm_count is None:
            short_name = module_name.split(".")[-1]
            perm_count = perm_counts.get(short_name, 0)

        items.append({
            "name": metadata.name,
            "module_name": module_name,
            "description": metadata.description,
            "usage": metadata.usage,
            "group": metadata.extra.get("group"),
            "badge_color": metadata.extra.get("badge_color"),
            "perm_point_count": perm_count,
        })

    items.sort(key=lambda x: (x["group"] or "", x["name"]))
    return success(data={"items": items, "total": len(items)}, request=request)

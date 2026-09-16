"""
启动钩子：建表 + 同步权限点 + 播种管理员组

在 NoneBot 启动时自动执行：
1. 全库 schema 引导：创建 Base 上全部已注册模型的缺失表（含 9 个权限模型，
   也覆盖尚未有自己的建表钩子的模型）
2. 将内存 Registry 中的权限点同步到 permission_points 表
3. 确保 perm_admin 管理员组存在（仅在缺失时用 SUPERUSERS 播种初始成员）
"""
from nonebot import get_driver, logger

from src.common.database import get_session, ensure_tables
from src.common.permission.bootstrap import ensure_admin_group
from src.common.permission.registry import perm_registry
from src.common.permission.models import PermissionPoint

from sqlalchemy import select


@get_driver().on_startup
async def sync_permission_points():
    """启动时建表、同步权限点、播种管理员组"""
    # 1. 全量建表（幂等，仅创建不存在的表）
    await ensure_tables()

    # 2. 同步权限点
    points = perm_registry.get_all()
    if not points:
        logger.info("[permission] 没有需要同步的权限点")
    else:
        logger.info(f"[permission] 正在同步 {len(points)} 个权限点到数据库...")
        new_count = 0
        async with get_session() as session:
            for point in points:
                # 检查是否已存在
                stmt = select(PermissionPoint.id).where(
                    PermissionPoint.perm_key == point.key
                ).limit(1)
                result = await session.execute(stmt)
                if result.first() is not None:
                    continue

                session.add(PermissionPoint(
                    perm_key=point.key,
                    name=point.name,
                    description=point.description,
                    plugin_name=point.plugin_name,
                ))
                new_count += 1
                logger.debug(f"[permission] 注册权限点: {point.key}")

        logger.info(f"[permission] 权限点同步完成 (新增 {new_count} 个)")

    # 3. 播种管理员组（在权限点同步之后：它要绑定 permission_manager:manage）
    await ensure_admin_group()

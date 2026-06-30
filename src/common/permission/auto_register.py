"""
启动钩子：建表 + 同步权限点

在 NoneBot 启动时自动执行：
1. 确保 8 张权限表存在（CREATE TABLE IF NOT EXISTS）
2. 将内存 Registry 中的权限点同步到 permission_points 表
"""
from nonebot import get_driver, logger

from src.common.database import Base, engine, async_session_factory
from src.common.permission.registry import perm_registry
from src.common.permission.models import PermissionPoint

from sqlalchemy import select


@get_driver().on_startup
async def sync_permission_points():
    """启动时建表并同步权限点到数据库"""
    # 1. 建表（幂等，仅创建不存在的表）
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    # 2. 同步权限点
    points = perm_registry.get_all()
    if not points:
        logger.info("[permission] 没有需要同步的权限点")
        return

    logger.info(f"[permission] 正在同步 {len(points)} 个权限点到数据库...")
    async with async_session_factory() as session:
        new_count = 0
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

        if new_count > 0:
            await session.commit()

    logger.info(f"[permission] 权限点同步完成 (新增 {new_count} 个)")

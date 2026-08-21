"""
权限组群绑定查询

提供按权限组名称查询绑定的 QQ 群 ID 列表的功能，
用于定时推送等场景获取目标群。
"""
from sqlalchemy import select

from src.common.database import async_session_factory
from src.common.permission.models import PermissionGroup, GroupPermBinding


async def get_bound_group_ids(pg_name: str) -> list[int]:
    """查询绑定到指定权限组的所有 QQ 群 ID

    Args:
        pg_name: 权限组名称（如 "check_up_notify"）

    Returns:
        绑定的 QQ 群 ID 列表，无绑定时返回空列表
    """
    async with async_session_factory() as session:
        stmt = (
            select(GroupPermBinding.qq_group_id)
            .join(PermissionGroup, GroupPermBinding.permission_group_id == PermissionGroup.id)
            .where(PermissionGroup.name == pg_name)
        )
        result = await session.execute(stmt)
        return [row[0] for row in result.all()]

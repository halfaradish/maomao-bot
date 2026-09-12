"""一键退群插件 — 数据访问层

管理群组列表的存取（原 mass_kick.json → mass_kick_managed_groups 表）。
"""
from sqlalchemy import delete, select

from src.common.database import async_session_factory, current_env_tag
from src.common.models.mass_kick_models import MassKickManagedGroup


async def list_groups() -> list[int]:
    """返回当前环境的管理群组列表（按插入顺序）"""
    stmt = (
        select(MassKickManagedGroup.group_id)
        .where(MassKickManagedGroup.env_tag == current_env_tag())
        .order_by(MassKickManagedGroup.id)
    )
    async with async_session_factory() as session:
        return list((await session.execute(stmt)).scalars())


async def add_group(group_id: int) -> bool:
    """添加群组，已存在时返回 False"""
    env_tag = current_env_tag()
    async with async_session_factory() as session:
        exists = await session.scalar(
            select(MassKickManagedGroup.id).where(
                MassKickManagedGroup.env_tag == env_tag,
                MassKickManagedGroup.group_id == group_id,
            )
        )
        if exists is not None:
            return False
        session.add(MassKickManagedGroup(env_tag=env_tag, group_id=group_id))
        await session.commit()
        return True


async def remove_group(group_id: int) -> bool:
    """删除群组，不存在时返回 False"""
    async with async_session_factory() as session:
        result = await session.execute(
            delete(MassKickManagedGroup).where(
                MassKickManagedGroup.env_tag == current_env_tag(),
                MassKickManagedGroup.group_id == group_id,
            )
        )
        await session.commit()
        return result.rowcount > 0

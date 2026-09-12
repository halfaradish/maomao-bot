"""插件使用统计 — 数据访问层

明细插入、榜单聚合查询、过期清理与展示名映射。
"""
from datetime import datetime

from nonebot import get_driver, get_loaded_plugins, logger
from sqlalchemy import delete as sa_delete
from sqlalchemy import func, select

from src.common.database import async_session_factory
from src.common.models.plugin_usage_models import PluginUsageRecord


def current_env_tag() -> str:
    """当前运行环境标签（.env 的 ENVIRONMENT，如 prod/local）"""
    return get_driver().config.environment


async def insert_usage_record(module_name: str, user_id: int, group_id: int | None) -> None:
    """插入一条使用明细"""
    async with async_session_factory() as session:
        session.add(PluginUsageRecord(
            module_name=module_name,
            user_id=user_id,
            group_id=group_id,
            env_tag=current_env_tag(),
            used_at=datetime.now(),
        ))
        await session.commit()


async def query_ranking(
    start: datetime,
    end: datetime | None,
    env_tag: str | None,
    limit: int,
) -> list:
    """按插件聚合使用次数，降序返回 (module_name, use_count, last_used_at) 行

    env_tag 为 None 时不限环境（全环境口径）。
    """
    stmt = select(
        PluginUsageRecord.module_name,
        func.count(PluginUsageRecord.id).label("use_count"),
        func.max(PluginUsageRecord.used_at).label("last_used_at"),
    ).where(PluginUsageRecord.used_at >= start)
    if end is not None:
        stmt = stmt.where(PluginUsageRecord.used_at < end)
    if env_tag is not None:
        stmt = stmt.where(PluginUsageRecord.env_tag == env_tag)
    stmt = (
        stmt.group_by(PluginUsageRecord.module_name)
        .order_by(func.count(PluginUsageRecord.id).desc())
        .limit(limit)
    )
    async with async_session_factory() as session:
        return (await session.execute(stmt)).all()


async def delete_expired_records(before: datetime) -> int:
    """清理 before 之前的使用明细，返回删除行数"""
    async with async_session_factory() as session:
        result = await session.execute(
            sa_delete(PluginUsageRecord).where(PluginUsageRecord.used_at < before)
        )
        await session.commit()
        return result.rowcount


def build_display_names(module_names: set[str]) -> dict[str, str]:
    """module_name → 展示名：优先 PluginMetadata.name（中文名），已卸载插件回退短名"""
    name_map: dict[str, str] = {}
    for plugin in get_loaded_plugins():
        metadata = plugin.metadata
        display = (metadata.name if metadata else None) or plugin.module_name.split(".")[-1]
        name_map[plugin.module_name] = display
    return {m: name_map.get(m, m.split(".")[-1]) for m in module_names}

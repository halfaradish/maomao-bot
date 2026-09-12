"""duel 插件 — 数据访问层

标签别名映射（原 duel.json 的 map/quick_map → duel_tag_aliases 表，
双向冗余关系化后消失，反查走 UNIQUE(env_tag, alias)）与
每日一题状态（原 daily_problems → duel_daily_problem_state 表）。
"""
from datetime import date

from sqlalchemy import delete, select
from sqlalchemy.dialects.mysql import insert as mysql_insert

from src.common.database import async_session_factory, current_env_tag
from src.common.models.duel_models import DuelDailyProblemState, DuelTagAlias


async def get_alias_map() -> dict[str, list[str]]:
    """返回 {tag: [alias, ...]}（原 map 结构），按插入顺序"""
    stmt = (
        select(DuelTagAlias.tag, DuelTagAlias.alias)
        .where(DuelTagAlias.env_tag == current_env_tag())
        .order_by(DuelTagAlias.id)
    )
    async with async_session_factory() as session:
        rows = (await session.execute(stmt)).all()
    alias_map: dict[str, list[str]] = {}
    for tag, alias in rows:
        alias_map.setdefault(tag, []).append(alias)
    return alias_map


async def has_tag(tag: str) -> bool:
    """标签是否已存在于映射表中"""
    stmt = select(DuelTagAlias.id).where(
        DuelTagAlias.env_tag == current_env_tag(),
        DuelTagAlias.tag == tag,
    ).limit(1)
    async with async_session_factory() as session:
        return await session.scalar(stmt) is not None


async def resolve_alias(alias: str) -> str | None:
    """反查别名归属的标签（原 quick_map），无映射时返回 None"""
    stmt = select(DuelTagAlias.tag).where(
        DuelTagAlias.env_tag == current_env_tag(),
        DuelTagAlias.alias == alias,
    )
    async with async_session_factory() as session:
        return await session.scalar(stmt)


async def add_alias(tag: str, alias: str) -> bool:
    """为标签添加别名；别名已被任何标签占用时返回 False

    比原 JSON 实现更严格：原实现中别名被写入 quick_map 时会静默
    覆盖其他标签的同名别名，造成 map/quick_map 不一致；数据库的
    UNIQUE(env_tag, alias) 约束使这种情况显式失败。
    """
    if await resolve_alias(alias) is not None:
        return False
    async with async_session_factory() as session:
        session.add(DuelTagAlias(env_tag=current_env_tag(), tag=tag, alias=alias))
        await session.commit()
    return True


async def remove_alias(tag: str, alias: str) -> bool:
    """删除标签下的别名；该别名不归属此标签时返回 False"""
    async with async_session_factory() as session:
        result = await session.execute(
            delete(DuelTagAlias).where(
                DuelTagAlias.env_tag == current_env_tag(),
                DuelTagAlias.tag == tag,
                DuelTagAlias.alias == alias,
            )
        )
        await session.commit()
        return result.rowcount > 0


async def get_daily_state() -> DuelDailyProblemState | None:
    """获取当前环境的每日一题状态行"""
    stmt = select(DuelDailyProblemState).where(
        DuelDailyProblemState.env_tag == current_env_tag()
    )
    async with async_session_factory() as session:
        return await session.scalar(stmt)


async def save_daily_state(current_date: date, current_problem: int, history: list[int]) -> None:
    """保存每日一题状态（每环境单行，upsert）"""
    stmt = mysql_insert(DuelDailyProblemState).values(
        env_tag=current_env_tag(),
        current_date=current_date,
        current_problem=current_problem,
        history=history,
    )
    stmt = stmt.on_duplicate_key_update(
        current_date=stmt.inserted.current_date,
        current_problem=stmt.inserted.current_problem,
        history=stmt.inserted.history,
    )
    async with async_session_factory() as session:
        await session.execute(stmt)
        await session.commit()

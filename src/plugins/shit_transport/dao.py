"""搬史插件 — 数据访问层

使用频率统计的存取（原 shit_transport.json 的 banshi/postshi 统计 dict
→ shit_transport_stats 表）。
"""
from typing import Any

from sqlalchemy import select
from sqlalchemy.dialects.mysql import insert as mysql_insert

from src.common.database import current_env_tag, get_session
from src.common.models.shit_transport_models import ShitTransportStats

KIND_BANSHI = "banshi"    # 转发发起人
KIND_POSTSHI = "postshi"  # 被引用消息作者


async def incr_stats(user_id: int, kind: str, nickname: str) -> None:
    """递增用户在指定维度的使用次数，并刷新为最新昵称（upsert）"""
    stmt = mysql_insert(ShitTransportStats).values(
        env_tag=current_env_tag(),
        user_id=user_id,
        kind=kind,
        count=1,
        nickname=nickname,
    )
    stmt = stmt.on_duplicate_key_update(
        count=ShitTransportStats.count + 1,
        nickname=stmt.inserted.nickname,
    )
    async with get_session() as session:
        await session.execute(stmt)


async def get_stats(kind: str) -> dict[str, dict[str, Any]]:
    """返回指定维度的统计，保持原 JSON 形状：{str(user_id): {"count": n, "nickname": nick}}"""
    stmt = select(
        ShitTransportStats.user_id,
        ShitTransportStats.count,
        ShitTransportStats.nickname,
    ).where(
        ShitTransportStats.env_tag == current_env_tag(),
        ShitTransportStats.kind == kind,
    )
    async with get_session(commit=False) as session:
        rows = (await session.execute(stmt)).all()
    return {
        str(user_id): {"count": count, "nickname": nickname}
        for user_id, count, nickname in rows
    }

"""伪消息插件 — 数据访问层

每日使用配额计数（原 fakemsg.json 的 daily_times_log → fakemsg_daily_usage 表）。
按 usage_date 维度天然隔离，无需整体重置；last_refresh_date 键已消失。
"""
import datetime

from sqlalchemy import delete, select
from sqlalchemy.dialects.mysql import insert as mysql_insert

from src.common.database import current_env_tag, get_session
from src.common.models.fakemsg_models import FakemsgDailyUsage


async def get_count(user_id: int, usage_date: datetime.date) -> int:
    """获取用户在指定日期的使用次数"""
    stmt = select(FakemsgDailyUsage.count).where(
        FakemsgDailyUsage.env_tag == current_env_tag(),
        FakemsgDailyUsage.user_id == user_id,
        FakemsgDailyUsage.usage_date == usage_date,
    )
    async with get_session(commit=False) as session:
        return await session.scalar(stmt) or 0


async def incr(user_id: int, usage_date: datetime.date) -> None:
    """指定日期使用次数 +1（原子 upsert）"""
    stmt = mysql_insert(FakemsgDailyUsage).values(
        env_tag=current_env_tag(),
        user_id=user_id,
        usage_date=usage_date,
        count=1,
    )
    stmt = stmt.on_duplicate_key_update(count=FakemsgDailyUsage.count + 1)
    async with get_session() as session:
        await session.execute(stmt)


async def delete_before(before: datetime.date) -> int:
    """清理当前环境 before 之前（不含）的历史计数行，返回删除行数"""
    async with get_session() as session:
        result = await session.execute(
            delete(FakemsgDailyUsage).where(
                FakemsgDailyUsage.env_tag == current_env_tag(),
                FakemsgDailyUsage.usage_date < before,
            )
        )
        return result.rowcount

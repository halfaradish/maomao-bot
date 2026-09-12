"""fakemsg 伪消息插件 — 每日使用配额计数模型（原 fakemsg.json 的 daily_times_log）"""
from datetime import date, datetime

from sqlalchemy import (
    BigInteger,
    Date,
    Index,
    Integer,
    String,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column

from src.common.database import Base


class FakemsgDailyUsage(Base):
    """非权限用户每日伪消息使用计数

    按 (env_tag, user_id, usage_date) 唯一；原 last_refresh_date 键被
    usage_date 维度取代（按日期查询天然自描述），历史日期行由定时任务清理。
    """

    __tablename__ = "fakemsg_daily_usage"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    env_tag: Mapped[str] = mapped_column(String(20))
    user_id: Mapped[int] = mapped_column(BigInteger)
    usage_date: Mapped[date] = mapped_column(Date)
    count: Mapped[int] = mapped_column(Integer, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.now)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.now, onupdate=datetime.now)

    __table_args__ = (
        UniqueConstraint("env_tag", "user_id", "usage_date", name="uq_fakemsg_daily_user"),
        Index("idx_fakemsg_usage_date", "usage_date"),
    )

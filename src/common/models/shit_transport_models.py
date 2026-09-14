"""shit_transport 搬史插件 — 使用频率统计模型（原 shit_transport.json 的两个统计 dict）"""
from datetime import datetime

from sqlalchemy import (
    BigInteger,
    DateTime,
    Integer,
    String,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column

from src.common.database import Base


class ShitTransportStats(Base):
    """搬史转发累计计数

    kind 区分统计维度：'banshi'（转发发起人）/ 'postshi'（被引用消息作者）。
    每次递增时 nickname 刷新为最新昵称。
    """

    __tablename__ = "shit_transport_stats"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    env_tag: Mapped[str] = mapped_column(String(20))
    user_id: Mapped[int] = mapped_column(BigInteger)
    kind: Mapped[str] = mapped_column(String(8))
    count: Mapped[int] = mapped_column(Integer, default=0)
    nickname: Mapped[str] = mapped_column(String(255), default="")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.now)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.now, onupdate=datetime.now)

    __table_args__ = (
        UniqueConstraint("env_tag", "user_id", "kind", name="uq_shit_transport_user_kind"),
    )

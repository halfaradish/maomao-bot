"""这就是VV 插件数据模型"""
from datetime import datetime

from sqlalchemy import BigInteger, DateTime, Index, Text
from sqlalchemy.orm import Mapped, mapped_column

from src.common.database import Base


class VvGroupBlacklist(Base):
    """vv 插件群黑名单 — 命中的群禁用 VV 表情包功能，未命中默认放行"""

    __tablename__ = "vv_group_blacklist"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    group_id: Mapped[int] = mapped_column(BigInteger, unique=True)
    reason: Mapped[str] = mapped_column(Text, default="")
    created_by: Mapped[int] = mapped_column(BigInteger)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.now)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.now, onupdate=datetime.now)

    __table_args__ = (
        Index("idx_vv_group_bl_id", "group_id"),
    )

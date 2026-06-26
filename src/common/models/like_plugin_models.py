"""
SQLAlchemy 声明式模型 — like_plugin 应用

与 Django like_plugin.models 中的 2 个模型一一对应，表名、字段类型
完全保持一致。
"""
from datetime import datetime

from sqlalchemy import BigInteger, Boolean, DateTime, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from src.common.database import Base


class LikeRecord(Base):
    __tablename__ = "like_plugin_likerecord"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    user_id: Mapped[str] = mapped_column(String(100), unique=True)
    nickname: Mapped[str | None] = mapped_column(String(255), nullable=True)
    count: Mapped[int] = mapped_column(Integer, default=0)
    is_following: Mapped[bool] = mapped_column(Boolean, default=False)
    group_number: Mapped[str | None] = mapped_column(String(100), nullable=True)
    group_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    subscription_source: Mapped[str] = mapped_column(String(255), default="diting_bot")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.now)


class PluginConfig(Base):
    __tablename__ = "like_plugin_pluginconfig"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    key: Mapped[str] = mapped_column(String(100), unique=True)
    value: Mapped[str] = mapped_column(Text)

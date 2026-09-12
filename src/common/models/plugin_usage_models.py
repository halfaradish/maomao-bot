"""插件使用频率统计 — 明细记录模型"""
from datetime import datetime

from sqlalchemy import BigInteger, DateTime, Index, String
from sqlalchemy.orm import Mapped, mapped_column

from src.common.database import Base


class PluginUsageRecord(Base):
    """插件使用明细 — handler 真正执行时记一行

    env_tag 隔离生产/测试共用数据库的数据（取自 ENVIRONMENT 环境变量）。
    """

    __tablename__ = "plugin_usage_records"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    module_name: Mapped[str] = mapped_column(String(255))
    user_id: Mapped[int] = mapped_column(BigInteger)
    group_id: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    env_tag: Mapped[str] = mapped_column(String(20))
    used_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.now)

    __table_args__ = (
        Index("idx_pur_used_at", "used_at"),
        Index("idx_pur_module_used", "module_name", "used_at"),
        Index("idx_pur_env_used", "env_tag", "used_at"),
    )

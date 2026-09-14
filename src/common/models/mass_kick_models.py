"""mass_kick 一键退群插件 — 受管群列表模型（原 mass_kick.json 的 managed_groups）"""
from datetime import datetime

from sqlalchemy import BigInteger, DateTime, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from src.common.database import Base


class MassKickManagedGroup(Base):
    """超级用户维护的一键退群目标群"""

    __tablename__ = "mass_kick_managed_groups"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    env_tag: Mapped[str] = mapped_column(String(20))
    group_id: Mapped[int] = mapped_column(BigInteger)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.now)

    __table_args__ = (
        UniqueConstraint("env_tag", "group_id", name="uq_mass_kick_group"),
    )

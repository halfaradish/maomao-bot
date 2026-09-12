"""duel 对决插件 — CF 标签别名与每日一题状态模型（原 duel.json）"""
from datetime import date, datetime

from sqlalchemy import (
    BigInteger,
    Date,
    DateTime,
    Index,
    Integer,
    JSON,
    String,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column

from src.common.database import Base


class DuelTagAlias(Base):
    """CF 标签别名映射（原 duel.json 的 map/quick_map）

    alias 全局唯一归属一个 tag（原 quick_map 为 {alias: tag} 反查索引，
    关系化后双向冗余消失，反查走 UNIQUE(env_tag, alias)）。
    """

    __tablename__ = "duel_tag_aliases"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    env_tag: Mapped[str] = mapped_column(String(20))
    tag: Mapped[str] = mapped_column(String(64))
    alias: Mapped[str] = mapped_column(String(64))
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.now)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.now, onupdate=datetime.now)

    __table_args__ = (
        UniqueConstraint("env_tag", "alias", name="uq_duel_alias"),
        Index("idx_duel_alias_tag", "env_tag", "tag"),
    )


class DuelDailyProblemState(Base):
    """每日一题状态（原 duel.json 的 daily_problems），每环境单行

    history 为已用题目 id 池（写频 ≤1 次/天，保留 JSON 列最贴切），
    题库耗尽时由业务逻辑清空重新累积。
    """

    __tablename__ = "duel_daily_problem_state"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    env_tag: Mapped[str] = mapped_column(String(20), unique=True, name="uq_duel_daily_env")
    current_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    current_problem: Mapped[int | None] = mapped_column(Integer, nullable=True)
    history: Mapped[list] = mapped_column(JSON, default=list)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.now, onupdate=datetime.now)

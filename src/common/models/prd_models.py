"""prd 需求待办插件 — 待办条目模型（原 prd.json 的 to_do）"""
from datetime import date, datetime

from sqlalchemy import (
    BigInteger,
    Boolean,
    Date,
    DateTime,
    Index,
    String,
    Text,
)
from sqlalchemy.orm import Mapped, mapped_column

from src.common.database import Base


class PrdTodo(Base):
    """PRD 需求条目，业务字段与原 JSON 的 to_do 元素一一对应

    group 为 MySQL 保留字，属性名用 group_name、列名仍映射为 group
    （仿 botdb_models.metadata_ 先例）。priority 仅由 html_gen 读取，
    插件命令从不写入，保留列以维持渲染保真。
    """

    __tablename__ = "prd_todos"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    env_tag: Mapped[str] = mapped_column(String(20))
    content: Mapped[str] = mapped_column(Text)
    finish: Mapped[bool] = mapped_column(Boolean, default=False)
    group_name: Mapped[str] = mapped_column("group", String(64), default="其他")
    priority: Mapped[str] = mapped_column(String(16), default="medium")
    create_by: Mapped[str] = mapped_column(String(255), default="")
    create_at: Mapped[date | None] = mapped_column(Date, nullable=True)
    last_modify_by: Mapped[str] = mapped_column(String(255), default="")
    last_modify_at: Mapped[date | None] = mapped_column(Date, nullable=True)
    finish_by: Mapped[str] = mapped_column(String(255), default="")
    finish_at: Mapped[date | None] = mapped_column(Date, nullable=True)
    assign_to: Mapped[str | None] = mapped_column(String(255), nullable=True)
    assign_at: Mapped[date | None] = mapped_column(Date, nullable=True)
    assign_by: Mapped[str | None] = mapped_column(String(255), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.now)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.now, onupdate=datetime.now)

    __table_args__ = (
        Index("idx_prd_todo_finish", "env_tag", "finish"),
    )

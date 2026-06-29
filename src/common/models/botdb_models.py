"""
SQLAlchemy 声明式模型 — botdb 应用

与 Django botdb.models 中的 11 个模型一一对应，表名、字段类型、
索引和约束完全保持一致。
"""
import uuid
from datetime import date, datetime

from sqlalchemy import (
    BigInteger,
    Boolean,
    Date,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    JSON,
    SmallInteger,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from src.common.database import Base


# ============================================================
# 1. MessageEventLog — 消息事件日志
# ============================================================
class MessageEventLog(Base):
    __tablename__ = "messages_event_logs"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    message_id: Mapped[int] = mapped_column(Integer, unique=True)
    self_id: Mapped[int] = mapped_column(BigInteger)
    user_id: Mapped[int] = mapped_column(BigInteger)
    message_type: Mapped[str] = mapped_column(String(10))
    group_id: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    sub_type: Mapped[str] = mapped_column(String(20))
    post_type: Mapped[str] = mapped_column(String(20), default="message")
    time: Mapped[int] = mapped_column(Integer)
    raw_message: Mapped[str] = mapped_column(Text)
    message_json: Mapped[dict] = mapped_column(JSON)
    to_me: Mapped[bool] = mapped_column(Boolean, default=False)
    reply_json: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    sender_nickname: Mapped[str] = mapped_column(String(100))
    sender_card: Mapped[str | None] = mapped_column(String(100), nullable=True)
    sender_sex: Mapped[str | None] = mapped_column(String(10), default="unknown", nullable=True)
    sender_age: Mapped[int | None] = mapped_column(SmallInteger, nullable=True)
    sender_role: Mapped[str] = mapped_column(String(10), default="member")
    anonymous_flag: Mapped[str | None] = mapped_column(String(100), nullable=True)
    anonymous_name: Mapped[str | None] = mapped_column(String(50), nullable=True)
    anonymous_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.now)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.now, onupdate=datetime.now)

    __table_args__ = (
        Index("idx_user_id", "user_id"),
        Index("idx_group_id", "group_id"),
        Index("idx_time", "time"),
        Index("idx_to_me", "to_me"),
        Index("idx_type_group", "message_type", "group_id"),
        Index("idx_created_at", "created_at"),
    )


# ============================================================
# 2. TodoReminder — 待办提醒
# ============================================================
class TodoReminder(Base):
    __tablename__ = "todo_reminders"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    group_id: Mapped[int] = mapped_column(BigInteger)
    user_id: Mapped[int] = mapped_column(BigInteger)
    target_user_id: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    content: Mapped[str] = mapped_column(Text)
    remind_time: Mapped[datetime] = mapped_column(DateTime)
    remind_type: Mapped[str] = mapped_column(String(20), default="once")
    status: Mapped[str] = mapped_column(String(20), default="pending")
    created_by: Mapped[int] = mapped_column(BigInteger)
    last_modified_by: Mapped[int] = mapped_column(BigInteger)
    advance_remind_minutes: Mapped[int] = mapped_column(Integer, default=0)
    advance_reminded: Mapped[bool] = mapped_column(Boolean, default=False)
    execution_count: Mapped[int] = mapped_column(Integer, default=0)
    executed_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.now)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.now, onupdate=datetime.now)

    # 关系
    logs: Mapped[list["TodoReminderLog"]] = relationship(
        "TodoReminderLog", back_populates="reminder", cascade="all, delete-orphan"
    )

    __table_args__ = (
        Index(None, "group_id", "status", "remind_time"),
        Index(None, "user_id", "group_id", "status"),
    )


# ============================================================
# 3. TodoReminderLog — 提醒执行日志
# ============================================================
class TodoReminderLog(Base):
    __tablename__ = "todo_reminder_logs"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    reminder_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("todo_reminders.id", ondelete="CASCADE")
    )
    status: Mapped[str] = mapped_column(String(20))
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    execution_duration_ms: Mapped[int | None] = mapped_column(Integer, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.now)

    reminder: Mapped["TodoReminder"] = relationship("TodoReminder", back_populates="logs")

    __table_args__ = (
        Index(None, "reminder_id", "status"),
    )


# ============================================================
# 4. QQRobotMessage — 机器人消息
# ============================================================
class QQRobotMessage(Base):
    __tablename__ = "qq_robot_messages"

    # 保持与 Django TextChoices 相同的常量接口
    class SceneType:
        GROUP = "group"
        GUILD = "guild"
        PRIVATE = "private"

    class MessageStatus:
        SENT = "sent"
        CLOSED = "closed"
        CANCELLED = "cancelled"

    id: Mapped[str] = mapped_column(
        String(32), primary_key=True, default=lambda: uuid.uuid4().hex
    )
    bot_uin: Mapped[int] = mapped_column(BigInteger)
    scene_type: Mapped[str] = mapped_column(String(10))
    group_id: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    guild_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    channel_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    msg_seq: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    msg_id: Mapped[str | None] = mapped_column(String(128), nullable=True)
    content: Mapped[str] = mapped_column(Text)
    attachment: Mapped[dict] = mapped_column(JSON, default=dict)
    target_members: Mapped[list] = mapped_column(JSON, default=list)
    sent_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.now)
    remind_rule: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    status: Mapped[str] = mapped_column(String(20), default="sent")
    metadata_: Mapped[dict] = mapped_column("metadata", JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.now)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.now, onupdate=datetime.now)

    # 关系
    reactions: Mapped[list["QQMessageReaction"]] = relationship(
        "QQMessageReaction", back_populates="message", cascade="all, delete-orphan"
    )
    receipt_summary: Mapped["QQMessageReceiptSummary | None"] = relationship(
        "QQMessageReceiptSummary", back_populates="message", cascade="all, delete-orphan", uselist=False
    )
    reminders: Mapped[list["QQMessageReminder"]] = relationship(
        "QQMessageReminder", back_populates="message", cascade="all, delete-orphan"
    )

    __table_args__ = (
        Index("idx_qq_msg_bot_uin", "bot_uin"),
        Index("idx_qq_msg_scene", "scene_type"),
        Index("idx_qq_msg_group", "group_id"),
        Index("idx_qq_msg_guild", "guild_id"),
        Index("idx_qq_msg_id", "msg_id"),
        Index("idx_qq_msg_status", "status"),
        Index("idx_qq_msg_sent_at", "sent_at"),
    )


# ============================================================
# 5. QQMessageReaction — 消息反应（表情回应）
# ============================================================
class QQMessageReaction(Base):
    __tablename__ = "qq_message_reactions"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    message_id: Mapped[str] = mapped_column(
        String(32), ForeignKey("qq_robot_messages.id", ondelete="CASCADE")
    )
    reactor_uin: Mapped[int] = mapped_column(BigInteger)
    reaction_type: Mapped[str] = mapped_column(String(64))
    reacted_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.now)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.now, onupdate=datetime.now)
    raw_event: Mapped[dict] = mapped_column(JSON, default=dict)

    message: Mapped["QQRobotMessage"] = relationship("QQRobotMessage", back_populates="reactions")

    __table_args__ = (
        UniqueConstraint("message_id", "reactor_uin", name="uq_qq_message_reactor"),
        Index("idx_qq_react_reactor", "reactor_uin"),
        Index("idx_qq_react_type", "reaction_type"),
    )


# ============================================================
# 6. QQMessageReceiptSummary — 消息送达摘要
# ============================================================
class QQMessageReceiptSummary(Base):
    __tablename__ = "qq_message_receipt_summary"

    message_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("qq_robot_messages.id", ondelete="CASCADE"),
        primary_key=True,
    )
    expected_count: Mapped[int] = mapped_column(Integer, default=0)
    confirmed_count: Mapped[int] = mapped_column(Integer, default=0)
    outstanding_members: Mapped[list] = mapped_column(JSON, default=list)
    last_checked_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    reminder_stage: Mapped[int] = mapped_column(Integer, default=0)
    next_reminder_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.now)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.now, onupdate=datetime.now)

    message: Mapped["QQRobotMessage"] = relationship(
        "QQRobotMessage", back_populates="receipt_summary"
    )

    __table_args__ = (
        Index("idx_qq_receipt_expected", "expected_count"),
        Index("idx_qq_receipt_confirmed", "confirmed_count"),
        Index("idx_qq_receipt_next", "next_reminder_at"),
    )


# ============================================================
# 7. QQMessageReminder — 消息提醒
# ============================================================
class QQMessageReminder(Base):
    __tablename__ = "qq_message_reminders"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    message_id: Mapped[str] = mapped_column(
        String(32), ForeignKey("qq_robot_messages.id", ondelete="CASCADE")
    )
    reminder_type: Mapped[str] = mapped_column(String(20), default="group")
    payload: Mapped[dict] = mapped_column(JSON, default=dict)
    triggered_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.now)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.now)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.now, onupdate=datetime.now)

    message: Mapped["QQRobotMessage"] = relationship("QQRobotMessage", back_populates="reminders")

    __table_args__ = (
        Index("idx_qq_reminder_type", "reminder_type"),
        Index("idx_qq_reminder_triggered", "triggered_at"),
    )


# ============================================================
# 8. Group — 用户分组
# ============================================================
class Group(Base):
    __tablename__ = "group"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(64), unique=True)
    display_name: Mapped[str] = mapped_column(String(128), default="")
    description: Mapped[str] = mapped_column(Text, default="")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.now)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.now, onupdate=datetime.now)

    members: Mapped[list["GroupMember"]] = relationship(
        "GroupMember", back_populates="group", cascade="all, delete-orphan",
        foreign_keys="GroupMember.group_name",
    )


# ============================================================
# 9. GroupMember — 分组成员
# ============================================================
class GroupMember(Base):
    __tablename__ = "group_member"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    group_name: Mapped[str] = mapped_column(
        String(64), ForeignKey("group.name", ondelete="CASCADE")
    )
    qq_id: Mapped[int] = mapped_column(BigInteger)
    qq_nickname: Mapped[str] = mapped_column(String(255), default="")
    added_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.now)

    group: Mapped["Group"] = relationship(
        "Group", back_populates="members", foreign_keys=[group_name]
    )

    __table_args__ = (
        UniqueConstraint("group_name", "qq_id", name="group_member_group_name_qq_id_uniq"),
        Index(None, "qq_id"),
    )


# ============================================================
# 10. MonitoredGroup — QQ群监控列表
# ============================================================
class MonitoredGroup(Base):
    __tablename__ = "monitored_groups"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    group_id: Mapped[int] = mapped_column(BigInteger, unique=True)
    group_name: Mapped[str] = mapped_column(String(100), default="")
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.now)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.now, onupdate=datetime.now)

    files: Mapped[list["GroupFile"]] = relationship(
        "GroupFile", back_populates="group", cascade="all, delete-orphan"
    )

    __table_args__ = (
        Index("idx_monitored_group_id", "group_id"),
        Index("idx_monitored_is_active", "is_active"),
    )


# ============================================================
# 11. GroupFile — 群文件记录
# ============================================================
class GroupFile(Base):
    __tablename__ = "group_files"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    group_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("monitored_groups.group_id", ondelete="CASCADE")
    )
    file_id: Mapped[str] = mapped_column(String(100))
    file_name: Mapped[str] = mapped_column(String(255))
    file_size: Mapped[int] = mapped_column(BigInteger, default=0)
    file_path: Mapped[str] = mapped_column(String(500))
    file_hash: Mapped[str] = mapped_column(String(32), index=True)
    uploader_id: Mapped[int] = mapped_column(BigInteger, default=0)
    upload_time: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    downloaded_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.now)

    group: Mapped["MonitoredGroup"] = relationship("MonitoredGroup", back_populates="files")

    __table_args__ = (
        UniqueConstraint("file_id", "group_id", name="uq_file_per_group"),
        Index("idx_file_hash", "file_hash"),
        Index("idx_group_downloaded", "group_id", "downloaded_at"),
    )


# ============================================================
# 12. GroupStatistic — 群统计信息
# ============================================================
class GroupStatistic(Base):
    __tablename__ = "group_statistics"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    group_id: Mapped[str] = mapped_column(String(20), unique=True, nullable=False)
    group_name: Mapped[str] = mapped_column(String(100), nullable=False)
    group_function: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.now)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.now, onupdate=datetime.now)


# ============================================================
# 13. CustomHoliday — 自定义节假日
# ============================================================
class CustomHoliday(Base):
    __tablename__ = "custom_holiday"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    date: Mapped[date] = mapped_column(Date, nullable=False, unique=True)
    name: Mapped[str] = mapped_column(String(64), nullable=False)
    is_off_day: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    is_enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.now)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.now, onupdate=datetime.now)

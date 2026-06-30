"""
权限系统 SQLAlchemy 声明式模型

8 张表，涵盖权限点、黑白名单、权限组及群绑定。
表名、字段类型、索引和约束与 botdb_models.py 保持一致。
"""
from datetime import datetime

from sqlalchemy import (
    BigInteger,
    DateTime,
    ForeignKey,
    Index,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from src.common.database import Base


# ============================================================
# 1. PermissionPoint — 插件自动注册的权限点
# ============================================================
class PermissionPoint(Base):
    __tablename__ = "permission_points"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    plugin_name: Mapped[str] = mapped_column(String(100))
    perm_key: Mapped[str] = mapped_column(String(200), unique=True)
    name: Mapped[str] = mapped_column(String(100))
    description: Mapped[str] = mapped_column(Text, default="")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.now)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.now, onupdate=datetime.now)

    __table_args__ = (
        Index("idx_perm_plugin", "plugin_name"),
        Index("idx_perm_key", "perm_key"),
    )


# ============================================================
# 2. UserBlacklist — 用户黑名单
# ============================================================
class UserBlacklist(Base):
    __tablename__ = "user_blacklist"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(BigInteger, unique=True)
    reason: Mapped[str] = mapped_column(Text, default="")
    created_by: Mapped[int] = mapped_column(BigInteger)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.now)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.now, onupdate=datetime.now)

    __table_args__ = (
        Index("idx_user_bl_id", "user_id"),
    )


# ============================================================
# 3. GroupBlacklist — 群黑名单
# ============================================================
class GroupBlacklist(Base):
    __tablename__ = "group_blacklist"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    group_id: Mapped[int] = mapped_column(BigInteger, unique=True)
    reason: Mapped[str] = mapped_column(Text, default="")
    created_by: Mapped[int] = mapped_column(BigInteger)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.now)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.now, onupdate=datetime.now)

    __table_args__ = (
        Index("idx_group_bl_id", "group_id"),
    )


# ============================================================
# 4. UserWhitelist — 用户白名单
# ============================================================
class UserWhitelist(Base):
    __tablename__ = "user_whitelist"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(BigInteger, unique=True)
    reason: Mapped[str] = mapped_column(Text, default="")
    created_by: Mapped[int] = mapped_column(BigInteger)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.now)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.now, onupdate=datetime.now)

    __table_args__ = (
        Index("idx_user_wl_id", "user_id"),
    )


# ============================================================
# 5. GroupWhitelist — 群白名单
# ============================================================
class GroupWhitelist(Base):
    __tablename__ = "group_whitelist"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    group_id: Mapped[int] = mapped_column(BigInteger, unique=True)
    reason: Mapped[str] = mapped_column(Text, default="")
    created_by: Mapped[int] = mapped_column(BigInteger)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.now)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.now, onupdate=datetime.now)

    __table_args__ = (
        Index("idx_group_wl_id", "group_id"),
    )


# ============================================================
# 6. PermissionGroup — 权限组/角色定义
# ============================================================
class PermissionGroup(Base):
    __tablename__ = "permission_groups"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(100), unique=True)
    display_name: Mapped[str] = mapped_column(String(200), default="")
    description: Mapped[str] = mapped_column(Text, default="")
    created_by: Mapped[int] = mapped_column(BigInteger)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.now)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.now, onupdate=datetime.now)

    # 关系
    members: Mapped[list["PermissionGroupMember"]] = relationship(
        "PermissionGroupMember", back_populates="group", cascade="all, delete-orphan"
    )
    permissions: Mapped[list["PermissionGroupPerm"]] = relationship(
        "PermissionGroupPerm", back_populates="group", cascade="all, delete-orphan"
    )


# ============================================================
# 7. PermissionGroupMember — 权限组成员
# ============================================================
class PermissionGroupMember(Base):
    __tablename__ = "permission_group_members"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    group_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("permission_groups.id", ondelete="CASCADE")
    )
    user_id: Mapped[int] = mapped_column(BigInteger)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.now)

    group: Mapped["PermissionGroup"] = relationship("PermissionGroup", back_populates="members")

    __table_args__ = (
        UniqueConstraint("group_id", "user_id", name="uq_pg_member"),
        Index("idx_pg_member_uid", "user_id"),
        Index("idx_pg_member_gid", "group_id"),
    )


# ============================================================
# 8. PermissionGroupPerm — 权限组绑定的权限点
# ============================================================
class PermissionGroupPerm(Base):
    __tablename__ = "permission_group_perms"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    group_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("permission_groups.id", ondelete="CASCADE")
    )
    perm_key: Mapped[str] = mapped_column(String(200))
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.now)

    group: Mapped["PermissionGroup"] = relationship("PermissionGroup", back_populates="permissions")

    __table_args__ = (
        UniqueConstraint("group_id", "perm_key", name="uq_pg_perm"),
        Index("idx_pg_perm_gid", "group_id"),
        Index("idx_pg_perm_key", "perm_key"),
    )


# ============================================================
# 9. GroupPermBinding — QQ 群与权限组的绑定
# ============================================================
class GroupPermBinding(Base):
    __tablename__ = "group_perm_bindings"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    qq_group_id: Mapped[int] = mapped_column(BigInteger)
    permission_group_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("permission_groups.id", ondelete="CASCADE")
    )
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.now)

    __table_args__ = (
        UniqueConstraint("qq_group_id", "permission_group_id", name="uq_group_binding"),
        Index("idx_gpb_qq_gid", "qq_group_id"),
        Index("idx_gpb_pg_id", "permission_group_id"),
    )

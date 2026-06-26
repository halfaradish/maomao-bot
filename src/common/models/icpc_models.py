"""
ICPC 数据库 SQLAlchemy 模型

仅覆盖插件查询中引用的列，不强制要求匹配完整的 MySQL 表结构。
所有模型继承 IcpcBase（独立于 Bot DB 的 Base）。

表清单：
- ding_checkup        考勤打卡记录
- cf_official_problems Codeforces 官方题库
- user                用户/队员信息
- oj_account          OJ 账号映射
- cf_all_submissions  Codeforces 全部提交记录
- luogu_all_submissions 洛谷全部提交记录
"""
from datetime import date, datetime

from sqlalchemy import BigInteger, Date, DateTime, Integer, JSON, String
from sqlalchemy.orm import Mapped, mapped_column

from src.common.icpc_database import IcpcBase


class DingCheckup(IcpcBase):
    """考勤打卡记录表"""
    __tablename__ = "ding_checkup"

    name: Mapped[str] = mapped_column(String(128), primary_key=True)
    time: Mapped[datetime] = mapped_column(DateTime, primary_key=True)
    check_type: Mapped[str] = mapped_column(String(32))


class CfOfficialProblem(IcpcBase):
    """Codeforces 官方题库表"""
    __tablename__ = "cf_official_problems"

    problem_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    rating: Mapped[int | None] = mapped_column(Integer, nullable=True)
    tags: Mapped[dict | None] = mapped_column(JSON, nullable=True)


class IcpcUser(IcpcBase):
    """用户/队员信息表"""
    __tablename__ = "user"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    real_name: Mapped[str | None] = mapped_column(String(128), nullable=True)
    school: Mapped[str | None] = mapped_column(String(128), nullable=True)
    role_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    enter_time: Mapped[date | None] = mapped_column(Date, nullable=True)


class OjAccount(IcpcBase):
    """OJ 账号映射表"""
    __tablename__ = "oj_account"

    user_id: Mapped[int] = mapped_column(Integer, primary_key=True)
    cf_account: Mapped[str | None] = mapped_column(String(128), nullable=True)
    luogu_uid: Mapped[str | None] = mapped_column(String(64), nullable=True)


class CfAllSubmission(IcpcBase):
    """Codeforces 全部提交记录表"""
    __tablename__ = "cf_all_submissions"

    sub_id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    account: Mapped[str | None] = mapped_column(String(128), nullable=True)
    problem_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    problem_name: Mapped[str | None] = mapped_column(String(256), nullable=True)
    rating: Mapped[int | None] = mapped_column(Integer, nullable=True)
    creation_time: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    verdict: Mapped[str | None] = mapped_column(String(64), nullable=True)


class LuoguAllSubmission(IcpcBase):
    """洛谷全部提交记录表"""
    __tablename__ = "luogu_all_submissions"

    sub_id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    uid: Mapped[str | None] = mapped_column(String(64), nullable=True)
    problem_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    problem_name: Mapped[str | None] = mapped_column(String(256), nullable=True)
    difficulty: Mapped[int | None] = mapped_column(Integer, nullable=True)
    creation_time: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    is_pass: Mapped[int | None] = mapped_column(Integer, nullable=True)

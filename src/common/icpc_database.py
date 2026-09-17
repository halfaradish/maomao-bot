"""
SQLAlchemy 异步引擎与会话工厂 — ICPC 数据库

为 ICPC（竞赛）数据库提供独立的 SQLAlchemy 2.0 async 引擎和会话工厂，
与 Bot DB（database.py）完全分离。配置沿用 ICPC_DB_* 环境变量。
"""
from urllib.parse import quote

from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker
from sqlalchemy.orm import DeclarativeBase

from src.config.local_config import IcpcDBConfig


class IcpcBase(DeclarativeBase):
    """所有 ICPC 数据库模型的基类（独立于 Bot DB 的 Base）"""
    pass


def _build_icpc_async_db_url() -> str:
    """从环境变量构建 mysql+asyncmy 连接 URL"""
    return (
        f"mysql+asyncmy://{quote(IcpcDBConfig.ICPC_DB_USER)}:{quote(IcpcDBConfig.ICPC_DB_PASSWORD)}"
        f"@{IcpcDBConfig.ICPC_DB_HOST}:{IcpcDBConfig.ICPC_DB_PORT}"
        f"/{IcpcDBConfig.ICPC_DB_NAME}?charset=utf8mb4"
    )


ICPC_ASYNC_DB_URL = _build_icpc_async_db_url()

icpc_engine = create_async_engine(
    ICPC_ASYNC_DB_URL,
    echo=False,
    pool_pre_ping=True,
    # 远端 ICPC 库（172.16.40.37:3307）上的空闲连接存活时间明显短于 1 小时，
    # 取 300 秒可以让多数取出的连接本来就是新建立的，避免依赖失效连接的重试路径。
    pool_recycle=300,
    pool_size=IcpcDBConfig.ICPC_DB_POOL_SIZE,
    max_overflow=10,
)

icpc_async_session_factory = async_sessionmaker(
    icpc_engine,
    class_=AsyncSession,
    expire_on_commit=False,
)

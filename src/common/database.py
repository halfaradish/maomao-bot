"""
SQLAlchemy 异步引擎与会话工厂

替代 Django ORM，使用 asyncmy 驱动连接 MySQL。
配置沿用 BOT_DB_* 环境变量，与之前 Django 设置保持一致。
"""
import os
from urllib.parse import quote

from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker
from sqlalchemy.orm import DeclarativeBase

from src.config.local_config import DiTingBotDBConfig


class Base(DeclarativeBase):
    """所有 SQLAlchemy 模型的基类"""
    pass


def current_env_tag() -> str:
    """当前运行环境标签（.env 的 ENVIRONMENT，如 prod/dev），用于同库多环境数据隔离

    bot 运行时取 nonebot 配置；独立脚本（未 init nonebot）回退读 ENVIRONMENT 环境变量。
    """
    try:
        from nonebot import get_driver

        return get_driver().config.environment
    except Exception:
        return os.getenv("ENVIRONMENT", "dev")


def _build_async_db_url() -> str:
    """从环境变量构建 mysql+asyncmy 连接 URL"""
    return (
        f"mysql+asyncmy://{quote(DiTingBotDBConfig.BOT_DB_USER)}:{quote(DiTingBotDBConfig.BOT_DB_PASSWORD)}"
        f"@{DiTingBotDBConfig.BOT_DB_HOST}:{DiTingBotDBConfig.BOT_DB_PORT}"
        f"/{DiTingBotDBConfig.BOT_DB_NAME}?charset=utf8mb4"
    )


ASYNC_DB_URL = _build_async_db_url()

engine = create_async_engine(
    ASYNC_DB_URL,
    echo=False,
    pool_pre_ping=True,
    pool_recycle=3600,
    pool_size=DiTingBotDBConfig.BOT_DB_POOL_SIZE,
    max_overflow=10,
)

async_session_factory = async_sessionmaker(
    engine,
    class_=AsyncSession,
    expire_on_commit=False,
)

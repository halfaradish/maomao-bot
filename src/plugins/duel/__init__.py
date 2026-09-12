from nonebot import get_driver, get_plugin_config

from .config import Config
from .duel import __plugin_meta__
from . import dao  # noqa: F401 - 导入模型，确保建表钩子能创建 duel 表

config = get_plugin_config(Config)


@get_driver().on_startup
async def _create_tables():
    """建表（幂等，仅创建缺失表）"""
    from src.common.database import Base, engine

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

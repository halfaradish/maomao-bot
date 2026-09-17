from nonebot import get_driver, get_plugin_config

from .config import Config
from .duel import __plugin_meta__
from . import dao  # noqa: F401 - 导入模型，确保建表钩子能创建 duel 表
from . import permissions  # noqa: F401 — 注册权限点到权限系统

config = get_plugin_config(Config)


@get_driver().on_startup
async def _create_tables():
    """建表（幂等，仅创建缺失表）"""
    from src.common.database import ensure_tables
    from src.common.models.duel_models import DuelDailyProblemState, DuelStandardTag, DuelTagAlias

    await ensure_tables(DuelStandardTag, DuelTagAlias, DuelDailyProblemState)


@get_driver().on_startup
async def _ensure_default_perm_group():
    """确保本插件的默认权限组存在（幂等，不动已有成员）

    推题与查看映射是只读的（黑名单模式即可），只有写共享映射需要权限点，
    所以组名用 managers。
    """
    from src.common.permission import ensure_perm_group

    await ensure_perm_group(
        "duel_managers",
        "标签映射管理",
        ["duel:manage_map"],
        description="自动创建：添加/删除题目标签别名映射的权限",
    )

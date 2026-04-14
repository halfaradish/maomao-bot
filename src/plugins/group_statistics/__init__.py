from nonebot import (
    get_driver,
    logger
)
from nonebot.plugin import PluginMetadata

from .database import db_manager
from .config import Config
from ..cmd_list.model import PluginGroupEnum

# 导入commands模块以确保命令被注册
from . import commands

__plugin_meta__ = PluginMetadata(
    name="群统计",
    description="统计群聊信息并记录到数据库，支持添加、删除和查看群聊信息",
    usage="群统计 add 群号 群名 群功能 —— 添加群统计信息\n群统计 rm 群号 —— 删除群统计信息\n群统计 ls —— 查看所有群统计信息",
    config=Config,
    supported_adapters={"~onebot.v11"},
    extra={
        "group": PluginGroupEnum.GROUP_MANAGE.value,
        "badge_color": "blue"
    }
)

driver = get_driver()


@driver.on_startup
async def startup():
    """插件启动时执行的初始化操作"""
    logger.info("群统计插件正在启动...")
    try:
        # 确保数据库表存在
        db_manager.ensure_table_exists()
        logger.info("群统计插件初始化完成")
    except Exception as e:
        logger.error(f"群统计插件初始化失败: {e}")


@driver.on_shutdown
async def shutdown():
    """插件关闭时执行的清理操作"""
    logger.info("群统计插件正在关闭...")
    
    logger.info("群统计插件已关闭")


# 导出主要功能供其他插件使用
__all__ = ["db_manager", "commands"]

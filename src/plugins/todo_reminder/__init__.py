"""
Todo提醒插件
支持个人提醒、群组提醒、指定用户提醒等功能
"""

import os

from nonebot import require, logger
from nonebot.plugin import PluginMetadata

# 延迟加载插件依赖，避免在NoneBot未初始化时出错
try:
    require("nonebot_plugin_apscheduler")
except (ValueError, RuntimeError):
    # NoneBot未初始化或插件不存在时跳过
    pass

from .config import Config
from .database import TodoDatabase
from .time_parser import TimeParser
from .reminder_scheduler import ReminderScheduler
from .commands import TodoCommands
from src.common.model.model import PluginGroupEnum, PluginBadgeColor

__plugin_meta__ = PluginMetadata(
    name="Todo提醒插件",
    description="支持个人提醒、群组提醒、指定用户提醒等功能",
    usage="todo 30分钟后 开会 —— 创建30分钟后开会的提醒\ntodo list —— 查看所有提醒\ntodo cancel <id> —— 取消指定提醒\ntodo clear —— 清除所有提醒",
    type="application",
    config=Config,
    supported_adapters={"~onebot.v11"},
    extra={
        "author": "Your Name",
        "version": "1.0.0",
        "priority": 10,
        "group": PluginGroupEnum.UTILITY.value,
        "badge_color": PluginBadgeColor.GREEN.value
    },
)

# 通过环境变量控制插件开关
_todo_cmd_enabled = os.getenv("TODO_CMD_ENABLE", "true").lower() in (
    "1",
    "true",
    "yes",
    "on",
)

if _todo_cmd_enabled:
    # 初始化配置
    config = Config()

    # 初始化数据库
    db = TodoDatabase()

    # 初始化时间解析器
    time_parser = TimeParser()

    # 初始化提醒调度器
    scheduler = ReminderScheduler(db, time_parser)

    # 初始化命令处理器
    commands = TodoCommands(db, time_parser, scheduler, config)

    # 导入主入口以注册命令
    from . import main  # noqa: F401

    logger.info("Todo提醒插件已启用 (TODO_CMD_ENABLE=true)")
else:
    config = None
    db = None
    time_parser = None
    scheduler = None
    commands = None
    logger.warning("Todo提醒插件已禁用 (TODO_CMD_ENABLE=false)")

# 导出主要功能
__all__ = [
    "config",
    "db", 
    "time_parser",
    "scheduler",
    "commands"
]
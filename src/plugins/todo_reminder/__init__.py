"""
Todo提醒插件
支持个人提醒、群组提醒、指定用户提醒等功能
"""

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

__plugin_meta__ = PluginMetadata(
    name="Todo提醒插件",
    description="支持个人提醒、群组提醒、指定用户提醒等功能",
    usage="提醒 明天下午3点 开会",
    type="application",
    homepage="https://github.com/your-repo/todo-reminder",
    supported_adapters={"~onebot.v11"},
    extra={
        "author": "Your Name",
        "version": "1.0.0",
        "priority": 10,
    },
)

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
from . import main

# 导出主要功能
__all__ = [
    "config",
    "db", 
    "time_parser",
    "scheduler",
    "commands"
]
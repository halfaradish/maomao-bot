import os

from nonebot.plugin import PluginMetadata
from src.common.plugin_meta import PluginGroupEnum, PluginBadgeColor

# ========== 添加插件开关（在这里插入） ==========
GROUP_FILE_MANAGER_ENABLED = os.getenv("GROUP_FILE_MANAGER_ENABLED", "true").lower() == "true"

if not GROUP_FILE_MANAGER_ENABLED:
    __plugin_meta__ = PluginMetadata(
        name="群文件管理（已禁用）",
        description="自动监控和管理群文件（当前已禁用，设置 GROUP_FILE_MANAGER_ENABLED=true 启用）",
        usage="此插件已在 .env 中禁用",
        supported_adapters={"~onebot.v11"},
        extra={
            "group": PluginGroupEnum.GROUP_MANAGE.value,
            "badge_color": PluginBadgeColor.BLUE.value
        }
    )
else:
    # handlers 注册全部命令 matcher 与上传监听；hooks 注册启动/bot连接钩子与定时任务
    from . import handlers, hooks  # noqa: F401

    __plugin_meta__ = PluginMetadata(
        name="群文件管理",
        description="自动监控和管理群文件，支持实时监听上传和历史文件爬取",
        usage="/今日文件 —— 查看今天收集到的新文件\n/文件位置 —— 查看文件存储位置\n/爬取历史文件 —— 手动触发历史文件爬取\n/添加监控群 —— 将当前群添加到监控列表\n/移除监控群 —— 将当前群从监控列表移除\n/监控群列表 —— 查看所有监控群",
        supported_adapters={"~onebot.v11"},
        extra={
            "group": PluginGroupEnum.GROUP_MANAGE.value,
            "badge_color": PluginBadgeColor.BLUE.value
        }
    )

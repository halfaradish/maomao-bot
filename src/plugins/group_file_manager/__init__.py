from nonebot.plugin import PluginMetadata

from src.common.plugin_guard import disabled_plugin_metadata, plugin_enabled
from src.common.plugin_meta import PluginGroupEnum, PluginBadgeColor

# 插件启停开关：禁用时只给存根元数据，不注册任何 handler
GROUP_FILE_MANAGER_ENABLED = plugin_enabled("GROUP_FILE_MANAGER_ENABLED")

if not GROUP_FILE_MANAGER_ENABLED:
    __plugin_meta__ = disabled_plugin_metadata(
        "GROUP_FILE_MANAGER_ENABLED",
        name="群文件管理",
        description="自动监控和管理群文件",
        group=PluginGroupEnum.GROUP_MANAGE,
        badge_color=PluginBadgeColor.BLUE,
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

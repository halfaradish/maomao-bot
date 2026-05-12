"""
nonebot项目启动时会立刻加载src/plugins内的插件
为确保谛听项目的api服务能在项目启动时便被加载
即设置ensure插件导入需要在启动时加载的服务
"""
from ...api import app
from nonebot.log import logger, default_format
from nonebot.plugin import PluginMetadata
from src.common.model.model import PluginGroupEnum, PluginBadgeColor

__plugin_meta__ = PluginMetadata(
    name="启动确保",
    description="确保API服务在项目启动时加载",
    usage="自动运行，无需手动操作",
    supported_adapters={"~onebot.v11"},
    extra={
        "group": PluginGroupEnum.BASE.value,
        "badge_color": PluginBadgeColor.GREEN.value
    }
)

logger.add(
    'logs/nonebot.log',
    rotation="00:00",
    retention="7 days",
    level="DEBUG",
    encoding="utf-8",
    format=default_format,
    enqueue=True,
    compression="zip"
)
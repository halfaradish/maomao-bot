"""插件运行期共享对象：配置实例与命令匹配器。

`perm_cmd` 必须只有这一个定义点——本包其余模块都从这里取它，否则会出现
多个匹配器实例。
"""
from nonebot import get_plugin_config, on_command

from .config import Config

config = get_plugin_config(Config)

perm_cmd = on_command(
    config.perm_mgr_command,
    aliases={'perm'},
    force_whitespace=True,
    priority=config.perm_mgr_priority,
    block=config.perm_mgr_block,
)

__all__ = ["config", "perm_cmd"]

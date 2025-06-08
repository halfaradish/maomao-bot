from nonebot import get_plugin_config, Bot, on_command, logger, get_driver
from nonebot.plugin import PluginMetadata
from nonebot.adapters.onebot.v11 import MessageEvent
from nonebot.adapters import Message
from nonebot.params import CommandArg

from .config import Config

global_config = get_driver().config
plugin_config = Config.parse_obj(global_config.dict())

__plugin_meta__ = PluginMetadata(
    name="cmd_list",
    description="",
    usage="",
    config=Config,
    supported_adapters={"~onebot.v11"}
)

config = get_plugin_config(Config)

cmd_list = on_command(
    "cmd",
    aliases={"命令", "help", "帮助"},
    priority=plugin_config.priority,
    block=plugin_config.block
)

@cmd_list.handle()
async def _(bot: Bot, event: MessageEvent, args: Message = CommandArg()):
    try:
        cmd_info_list = plugin_config.user_msg + plugin_config.editor_msg + plugin_config.admin_msg
        cmd_info = "\n".join(cmd_info_list)
        await bot.send(event=event, message=cmd_info)
    except Exception as e:
        logger.opt(exception=True).warning("[cmd_list]响应失败")
        await bot.send(event=event, message=f"响应失败:\n{e}")
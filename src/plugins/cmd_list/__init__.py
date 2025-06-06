from nonebot import get_plugin_config, Bot, on_command
from nonebot.plugin import PluginMetadata
from nonebot.adapters.onebot.v11 import MessageEvent, GroupMessageEvent, PrivateMessageEvent
from nonebot.adapters import Message
from nonebot.params import CommandArg
from nonebot import logger

from .config import Config
from ...config import local_config

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
    priority=Config.priority,
    block=Config.block
)

@cmd_list.handle()
async def _(bot: Bot, event: MessageEvent, args: Message = CommandArg()):
    try:
        cmd_list_msg = Config.user_msg + Config.editor_msg + Config.admin_msg
        await bot.send(event=event, message=cmd_list_msg)
    except Exception as e:
        logger.opt(exception=True).warning("响应失败")
        await bot.send(event=event, message="响应失败")
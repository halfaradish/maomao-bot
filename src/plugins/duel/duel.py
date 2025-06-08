from nonebot import Bot, on_command, logger, get_driver
from nonebot.plugin import PluginMetadata
from nonebot.adapters.onebot.v11 import MessageEvent
from nonebot.adapters import Message
from nonebot.params import CommandArg

from .config import Config
from .get_problem import get_one_problem_by_random

global_config = get_driver().config
plugin_config = Config.parse_obj(global_config.dict())

__plugin_meta__ = PluginMetadata(
    name="duel",
    description="",
    usage="",
    config=Config,
)

duel_command = on_command(
    "duel",
    aliases={"cf", "题目"},
    priority=plugin_config.priority,
    block=plugin_config.block
)

@duel_command.handle()
async def _(bot: Bot, event: MessageEvent, args: Message = CommandArg()):
    try:
        raw_args = args.extract_plain_text().strip()
        params = raw_args.strip() if raw_args else []

        if not params:
            raise TypeError("没有参数, 请输入参数")

        if params[0] == 'daily' or 'day':
            await bot.send(event=event, message=get_one_problem_by_random())

    except Exception as e:
        logger.opt(exception=True).warning("[duel]响应错误")
        await bot.send(event=event, message=f"响应错误:\n{e}")
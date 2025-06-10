from nonebot import Bot, on_command, logger, get_driver, get_plugin_config
from nonebot.plugin import PluginMetadata
from nonebot.adapters.onebot.v11 import MessageEvent
from nonebot.adapters import Message
from nonebot.params import CommandArg

from .config import Config
from .get_problem import get_one_problem_by_random, get_problem_id_by_rating_tags

plugin_config = get_plugin_config(Config)

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

async def vaildate_rating(bot: Bot, event: MessageEvent, rating_str: str):
    """判断rating是否为数字"""
    if not rating_str.isdigit():
        await bot.send(event=event, message=f"rating参数错误, 确保其为整数")
        return None
    return int(rating_str)

@duel_command.handle()
async def _(bot: Bot, event: MessageEvent, args: Message = CommandArg()):
    try:
        raw_args = args.extract_plain_text().strip()
        params = raw_args.strip() if raw_args else []

        if not params:
            await bot.send(event=event, message=plugin_config.DEFAULT_MSG)
            return

        if params[0] in ['daily', 'day']:
            await bot.send(event=event, message=get_one_problem_by_random())
            return
        elif params[0] == 'problem':
            rating = vaildate_rating(bot=bot, event=event, rating_str=params[1])
            tags = []
            for param in params[2:]:
                tags.append(param)
            await bot.send(event=event, message=get_problem_id_by_rating_tags(rating=rating, tags=tags))

    except Exception as e:
        logger.opt(exception=True).error("[duel]响应错误")
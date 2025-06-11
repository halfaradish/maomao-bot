from nonebot import Bot, on_command, logger, get_driver, get_plugin_config
from nonebot.plugin import PluginMetadata
from nonebot.adapters.onebot.v11 import MessageEvent
from nonebot.adapters import Message
from nonebot.params import CommandArg
import re

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

def text_msg_to_params(raw_args: str):
    parts = re.findall(r"(?<!\\)'(.*?)(?<!\\)'|(?<!\\)\"(.*?)(?<!\\)\"|(\S+)", raw_args)
    params = []
    for part in parts:
        for item in part:
            if item:
                params.append(item)
    return params

@duel_command.handle()
async def _(bot: Bot, event: MessageEvent, args: Message = CommandArg()):
    try:
        raw_args = args.extract_plain_text().strip()
        # params = raw_args.split() if raw_args else []
        params = text_msg_to_params(raw_args=raw_args)

        if not params:
            await bot.send(event=event, message=plugin_config.DEFAULT_MSG)
            return

        if params[0] in ['daily', 'day']:
            await bot.send(event=event, message=get_one_problem_by_random())
            return
        elif params[0] == 'problem':
            rating = await vaildate_rating(bot=bot, event=event, rating_str=params[1])
            tags = []
            if len(params) > 2:
                for param in params[2:]:
                    tags.append(param)
            await bot.send(event=event, message=get_problem_id_by_rating_tags(rating=rating, tags=tags))
            return
        else:
            await bot.send(event=event, message=f"位置命令: {params[0]}")
            return
    except Exception as e:
        logger.opt(exception=True).error("[duel]响应错误")
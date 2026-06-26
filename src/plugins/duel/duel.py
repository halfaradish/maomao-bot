from nonebot import Bot, on_command, logger, get_plugin_config
from nonebot.plugin import PluginMetadata
from nonebot.adapters.onebot.v11 import MessageEvent
from nonebot.adapters import Message
from nonebot.params import CommandArg
import re

from .config import Config
from .get_problem import get_one_problem_by_random, get_problem_id_by_rating_tags, get_daily_problem
from ...common.json_utils import JsonUtils
from src.common.model.model import PluginGroupEnum, PluginBadgeColor

plugin_config = get_plugin_config(Config)

__plugin_meta__ = PluginMetadata(
    name="竞赛对战",
    description="Codeforces 题目推荐插件，支持根据难度和标签推荐题目，以及每日一题功能",
    usage="/duel daily —— 获取每日一题\n/duel problem 难度 标签1 标签2... —— 根据难度和标签推荐题目\n/duel map tags —— 查看所有可用标签\n/duel map current —— 查看当前标签映射\n/duel map add 标签 别名 —— 添加标签别名映射\n/duel map remove 标签 别名 —— 删除标签别名映射",
    config=Config,
    supported_adapters={"~onebot.v11"},
    extra={
        "group": PluginGroupEnum.CONTEST.value,
        "badge_color": PluginBadgeColor.YELLOW.value
    }
)

duel_command = on_command(
    "duel",
    aliases={"cf推题", "题目"},
    priority=plugin_config.priority,
    block=plugin_config.block
)


class CommandHandler:
    @staticmethod
    def regex_search(str_list: list[str], pattern: str) -> list[str]:
        """对列表进行模糊搜索"""
        return [s for s in str_list if re.search(pattern, s, re.IGNORECASE)]

    @staticmethod
    def text_msg_to_params(raw_args: str) -> list[str]:
        """解析带引号的参数"""
        parts = re.findall(r"(?:^|\s)(?:'(.*?)'|\"(.*?)\"|(\S+))", raw_args)
        return [item for part in parts for item in part if item]

    @staticmethod
    async def handle_daily(bot: Bot, event: MessageEvent):
        """处理每日一题命令"""
        await bot.send(event=event, message=await get_daily_problem())

    @staticmethod
    async def handle_problem(bot: Bot, event: MessageEvent, params: list[str]):
        """处理题目查询命令"""
        if len(params) < 1:
            await bot.send(event=event,
                           message=f"该命令可在 problem 后可添加一个 rating 参数和多个 tag 参数。如\"duel problem 2300 dp 'binary search'，并根据输入的参数推题\"")
            return

        rating = None
        rating_cnt = 0
        tags = []
        for param in params:
            if param.isdigit():
                rating_cnt += 1
                if rating_cnt > 1:
                    await bot.send(event=event, message=f"该命令只接收一个 rating 参数，请检查参数{params}")
                    return
                rating = int(param)
            else:
                tags.append(param)

        if tags:
            data, _ = JsonUtils.read(plugin_config.filename, {
                "map": {},
                "quick_map": {}
            })
            tags_quick_map = data.get("quick_map", {})
            tags = [tags_quick_map.get(tag, tag) for tag in tags]

        await bot.send(event=event, message=await get_problem_id_by_rating_tags(rating, tags))

    @staticmethod
    def handle_map_tags(data: dict) -> str:
        """列出所有可用标签"""
        tags_map = data.get("map", {})
        return "\n".join(tags_map.keys())

    @staticmethod
    def handle_map_current(data: dict) -> str:
        """列出当前映射关系"""
        tags_map = data.get("map", {})
        if not tags_map:
            return "当前没有任何标签映射，请使用\n/duel map add\n命令添加新的映射。"

        lines = []
        for key, values in tags_map.items():
            if values:
                sub_msg = "".join(f"[{value}]" for value in values)
                lines.append(f"{key} -> {sub_msg}")
        return "\n".join(lines)

    @staticmethod
    async def handle_map_add(bot: Bot, event: MessageEvent, params: list[str], data: dict):
        """添加映射关系"""
        if len(params) != 2:
            await bot.send(event=event, message=f"参数个数有误！需要两个参数，实际收到{len(params)}个参数")
            return

        map_key, map_value = params
        tags_map = data.get("map", {})
        tags_quick_map = data.get("quick_map", {})

        if map_key not in tags_map:
            may_mention_key = CommandHandler.regex_search(list(tags_map.keys()), map_key)
            if not may_mention_key:
                msg = f"输入的参数 '{map_key}' 不在标准的 tags 中，请输入\n/duel map tags\n查看可映射的 tags"
            else:
                msg = f"输入的参数 '{map_key}' 不在标准的 tags 中\n是否在找{may_mention_key}?\n如果不是，请输入\n/duel map tags\n查看可映射的 tags"
            await bot.send(event=event, message=msg)
            return

        if map_value in tags_map[map_key]:
            await bot.send(event=event, message=f"当前映射已存在 '{map_key}' - '{map_value}'")
            return

        tags_map[map_key].append(map_value)
        tags_quick_map[map_value] = map_key
        JsonUtils.update(plugin_config.filename, {
            "map": tags_map,
            "quick_map": tags_quick_map
        })
        await bot.send(event=event,
                       message=f"映射键值对添加成功：'{map_key}' - '{map_value}'\n可通过\n/duel map current\n查看")

    @staticmethod
    async def handle_map_remove(bot: Bot, event: MessageEvent, params: list[str], data: dict):
        """删除映射关系"""
        if len(params) != 2:
            await bot.send(event=event, message=f"参数个数有误！需要两个参数，实际收到{len(params)}个参数")
            return

        map_key, map_value = params
        tags_map = data.get("map", {})
        tags_quick_map = data.get("quick_map", {})

        if map_key not in tags_map:
            may_mention_key = CommandHandler.regex_search(list(tags_map.keys()), map_key)
            if not may_mention_key:
                msg = f"输入的参数 '{map_key}' 不在标准的 tags 中，请输入\n/duel map tags\n查看可映射的 tags"
            else:
                msg = f"输入的参数 '{map_key}' 不在标准的 tags 中\n是否在找{may_mention_key}?\n如果不是，请输入\n/duel map tags\n查看可映射的 tags"
            await bot.send(event=event, message=msg)
            return

        if map_value not in tags_map[map_key]:
            await bot.send(event=event, message=f"当前映射不存在 '{map_key}' : '{map_value}'")
            return

        tags_map[map_key].remove(map_value)
        tags_quick_map.pop(map_value)
        JsonUtils.update(plugin_config.filename, {
            "map": tags_map,
            "quick_map": tags_quick_map
        })
        await bot.send(event=event, message=f"映射键值对删除成功：'{map_key}' : '{map_value}'")

    @staticmethod
    async def handle_map(bot: Bot, event: MessageEvent, params: list[str]):
        """处理映射命令"""
        data, _ = JsonUtils.read(plugin_config.filename, {
            "map": {},
            "quick_map": {}
        })

        if not params:
            await bot.send(event=event, message=plugin_config.MAP_DEFAULT_MSG)
            return

        subcommand = params[0]
        sub_params = params[1:]

        handlers = {
            "tags": lambda: bot.send(event=event, message=CommandHandler.handle_map_tags(data)),
            "current": lambda: bot.send(event=event, message=CommandHandler.handle_map_current(data)),
            "add": lambda: CommandHandler.handle_map_add(bot, event, sub_params, data),
            "rm": lambda: CommandHandler.handle_map_remove(bot, event, sub_params, data),
            "remove": lambda: CommandHandler.handle_map_remove(bot, event, sub_params, data)
        }

        if subcommand in handlers:
            handlers[subcommand]()
        else:
            await bot.send(event=event, message=f"map 后跟了未知参数: {subcommand}，请使用\n/duel map\n查看可用的命令")


@duel_command.handle()
async def handle_duel_command(bot: Bot, event: MessageEvent, args: Message = CommandArg()):
    try:
        raw_args = args.extract_plain_text().strip()
        params = CommandHandler.text_msg_to_params(raw_args) if raw_args else []

        if not params:
            await bot.send(event=event, message=plugin_config.DEFAULT_MSG)
            return

        command = params[0]
        command_params = params[1:]

        command_handlers = {
            "daily": lambda: CommandHandler.handle_daily(bot, event),
            "day": lambda: CommandHandler.handle_daily(bot, event),
            "problem": lambda: CommandHandler.handle_problem(bot, event, command_params),
            "题目": lambda: CommandHandler.handle_problem(bot, event, command_params),
            "map": lambda: CommandHandler.handle_map(bot, event, command_params),
            "映射": lambda: CommandHandler.handle_map(bot, event, command_params)
        }

        if command in command_handlers:
            await command_handlers[command]()
        else:
            await bot.send(event=event, message=f"未知命令: {command}")

    except Exception as e:
        logger.opt(exception=True).error(f"[duel]响应错误: {str(e)}")
from nonebot import Bot, on_command, logger, get_driver, get_plugin_config
from nonebot.plugin import PluginMetadata
from nonebot.adapters.onebot.v11 import MessageEvent
from nonebot.adapters import Message
from nonebot.params import CommandArg
import re

from .config import Config
from .get_problem import get_one_problem_by_random, get_problem_id_by_rating_tags
from ...common.json_utils import JsonUtils

plugin_config = get_plugin_config(Config)

__plugin_meta__ = PluginMetadata(
    name="duel",
    description="",
    usage="",
    config=Config,
)

duel_command = on_command(
    "duel",
    aliases={"cf推题", "题目"},
    priority=plugin_config.priority,
    block=plugin_config.block
)

def regex_search(str_list: list[str], pattern: str) -> list[str]:
    """对列表进行模糊搜索"""
    result = []
    for str in str_list:
        if re.search(pattern, str, re.IGNORECASE):
            result.append(str)
    return result

async def validate_rating(bot: Bot, event: MessageEvent, rating_str: str):
    """判断rating是否为数字"""
    if not rating_str.isdigit():
        await bot.send(event=event, message=f"rating参数错误, 确保其为整数")
        return None
    return int(rating_str)

def text_msg_to_params(raw_args: str):
    # parts = re.findall(r"(?<!\\)'(.*?)(?<!\\)'|(?<!\\)\"(.*?)(?<!\\)\"|(\S+)", raw_args)
    parts = re.findall(r"(?:^|\s)(?:'(.*?)'|\"(.*?)\"|(\S+))", raw_args)
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

        if params[0] in ['daily', 'day']: # 第一个参数为 daily 时
            await bot.send(event=event, message=get_one_problem_by_random())
            return
        elif params[0] in ['problem', '题目']: # 第一个参数为 problem 时
            rating = await validate_rating(bot=bot, event=event, rating_str=params[1])
            tags = []
            if len(params) > 2:
                for param in params[2:]:
                    tags.append(param)
            await bot.send(event=event, message=get_problem_id_by_rating_tags(rating=rating, tags=tags))
            return
        elif params[0] in ['map', '映射']: # 第一个参数为 map 时
            """映射相关操作"""
            map_opt_params = params[1:]
            # 没有 第二个参数 时, 时发送默认消息
            if not map_opt_params:
                await bot.send(event=event, message=plugin_config.MAP_DEFAULT_MSG)
            else:
                data, _ = JsonUtils.read(plugin_config.filename, {}) # 提取json中的数据
                tags_map: dict[str, list[str]] = data.get("map", {})
                for key in tags_map:
                    if not isinstance(tags_map[key], list):
                        tags_map[key] = []
                res_msg = ""
                # 当map后面的参数为tags时, 列出可添加映射的标签
                if map_opt_params[0] in ['tags', '标签']:
                    for key in tags_map:
                        res_msg += f"{key}\n"
                    await bot.send(event=event, message=res_msg)
                # 当map后面的参数为current时, 列出已经添加的映射
                elif map_opt_params[0] in ['current', '现存', '现存标签']:
                    for key in tags_map:
                        sub_msg = ""
                        values: list[str] = tags_map.get(key, "")
                        for value in values:
                            sub_msg += f"[{value}]"
                        res_msg += f"{key} -> {sub_msg}\n"
                    await bot.send(event=event, message=res_msg)
                # 当map后面的参数为add时，实行添加映射的操作
                elif map_opt_params[0] in ['add', '添加']:
                    if len(map_opt_params) != 3:
                        await bot.send(event=event, message=f"参数个数有误！！！\n该命令在add后面只接收两个参数，第一个为可映射的tag，第二个为tag的映射\n请检查当前参数：{map_opt_params}\n可以使用\"/duel map list\"查看可映射的tags")
                        return
                    map_key = map_opt_params[1]
                    map_value = map_opt_params[2]
                    # 如果输入的要映射的 tag 不在标准的 tags 中
                    if map_key not in tags_map:
                        may_mention_key: list[str] = regex_search(list(tags_map.keys()), map_key)
                        if not may_mention_key:
                            await bot.send(event=event, message=f"输入的参数 '{map_key}' 不在标准的 tags 中，请输入\"/duel map list\"查看可映射的tags")
                            return
                        else:
                            await bot.send(event=event, message=f"输入的参数 '{map_key}' 不在标准的 tags 中\n是否在找{may_mention_key}?\n如果不是，请输入\"/duel map list\"查看可映射的tags")
                            return
                    else:
                        if map_value in tags_map[map_key]:
                            await bot.send(event=event, message=f"当前映射已存在 '{map_key}' - '{map_value}'")
                        tags_map[map_key].append(map_value)
                        await bot.send(event=event, message=f"映射键值对添加成功：'{map_key}' - '{map_value}'\n可以通过\"/duel map current\"查看")
                        return
                # 当map后面的参数为rm时，实行删除映射的操作
                elif map_opt_params[0] in ['rm', 'remove', '删除']:
                    if len(map_opt_params) != 3:
                        await bot.send(event=event, message=f"参数个数有误！！！\n该命令在rm后面只接收两个参数，第一个为可映射的tag，第二个为tag的映射\n请检查当前参数：{map_opt_params}\n可以使用\"/duel map list\"查看可映射的tags")
                        return
                    map_key = map_opt_params[1]
                    map_value = map_opt_params[2]
                    if map_key not in tags_map:
                        may_mention_key: list[str] = regex_search(list(tags_map.keys()), map_key)
                        if not may_mention_key:
                            await bot.send(event=event, message=f"输入的参数 '{map_key}' 不在标准的 tags 中，请输入\"/duel map list\"查看可映射的tags")
                            return
                        else:
                            await bot.send(event=event, message=f"输入的参数 '{map_key}' 不在标准的 tags 中\n是否在找{may_mention_key}?\n如果不是，请输入\"/duel map list\"查看可映射的tags")
                            return
                    else:
                        if map_value in tags_map[map_key]:
                            tags_map[map_key].remove(map_value)
                            await bot.send(event=event, message=f"映射键值对删除成功：'{map_key}' - '{map_value}'")
                            return
                        else:
                            await bot.send(event=event, message=f"当前映射不存在 '{map_key}' - '{map_value}'")
        else:
            await bot.send(event=event, message=f"未知命令: {params[0]}")
            return
    except Exception as e:
        logger.opt(exception=True).error(f"[duel]响应错误: {str(e)}")
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

def rating_or_tag(bot: Bot, event: MessageEvent, confirmed_str: str):
    """判断是rating还是tag"""
    if not confirmed_str.isdigit():
        return confirmed_str
    return int(confirmed_str)

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
            problem_opt_params: str = params[1:]
            if not problem_opt_params:
                await bot.send(event=event, message=f"该命令可在 problem 后可添加一个 rating 参数和多个 tag 参数。如\"duel problem 2300 dp 'binary search'，并根据输入的参数推题\"")
                return
            rating = None
            rating_cnt: int = 0
            tags: list[str] = []
            for opt_param in problem_opt_params:
                if opt_param.isdigit():
                    rating_cnt += 1
                    if rating_cnt > 1:
                        await bot.send(event=event, message=f"该命令只接收一个 rating 参数，请检查参数{problem_opt_params}")
                        return
                    rating = int(opt_param)
                else:
                    tags.append(opt_param)
            if tags:
                data, _ = JsonUtils.read(plugin_config.filename, {})
                tags_quick_map: dict[str, list[str]] = data.get("quick_map", {})
                for i in range(len(tags)):
                    if tags[i] in tags_quick_map:
                        tags[i] = tags_quick_map.get(tags[i], "")
            res_msg = get_problem_id_by_rating_tags(rating=rating, tags=tags)
            #region
            # rating = rating_or_tag(bot=bot, event=event, confirmed_str=params[1])
            # tags: list[str] = []
            # if len(params) > 2:
            #     for param in params[2:]:
            #         tags.append(param)
            #     data, _ = JsonUtils.read(plugin_config.filename, {})
            #     tags_quick_map: dict[str, list[str]] = data.get("quick_map", {})
            #     for i in range(len(tags)):
            #         if tags[i] in tags_quick_map:  # 如果tags参数存在映射
            #             tags[i] = tags_quick_map.get(tags[i], "")
            #endregion
            await bot.send(event=event, message=res_msg)
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
                tags_quick_map: dict[str, str] = data.get("quick_map", {})
                for key in tags_map:
                    if not isinstance(tags_map[key], list):
                        tags_map[key] = []
                res_msg = ""
                # 当map后面的参数为tags时, 列出可添加映射的标签
                if map_opt_params[0] in ['tags', '标签']:
                    for key in tags_map:
                        res_msg += f"{key}\n"
                    await bot.send(event=event, message=res_msg.strip())
                    return
                # 当map后面的参数为current时, 列出已经添加的映射
                elif map_opt_params[0] in ['current', '现存', '现存标签']:
                    for key in tags_map:  # 遍历 map 中的所有键
                        sub_msg = ""
                        values: list[str] = tags_map.get(key, "")
                        if values:
                            for value in values:
                                sub_msg += f"[{value}]"
                            res_msg += f"{key} -> {sub_msg}\n"
                    if res_msg == "":
                        res_msg = "当前没有任何标签映射，请使用\n/duel map add\n命令添加新的映射。"
                    await bot.send(event=event, message=res_msg.strip())
                    return
                # 当map后面的参数为add时，实行添加映射的操作
                elif map_opt_params[0] in ['add', '添加']:
                    if len(map_opt_params) == 1:
                        await bot.send(event=eval, message=f"该命令在 add 后接收两个参数，第一个参数是存在的可映射的 tag ，第二个参数是 tag 的映射。如\"duel map add 'binary search' 二分\"")
                        return
                    elif len(map_opt_params) != 3:
                        await bot.send(event=event, message=f"参数个数有误！！！\n该命令在 add 后面只接收两个参数，请检查当前参数：{map_opt_params}\n可以使用命令\n/duel map add\n查看命令使用详细")
                        return
                    map_key = map_opt_params[1]
                    map_value = map_opt_params[2]
                    # 如果输入的要映射的 tag 不在标准的 tags 中
                    if map_key not in tags_map:
                        may_mention_key: list[str] = regex_search(list(tags_map.keys()), map_key)
                        if not may_mention_key:
                            await bot.send(event=event, message=f"输入的参数 '{map_key}' 不在标准的 tags 中，请输入\n/duel map tags\n查看可映射的 tags")
                            return
                        else:
                            await bot.send(event=event, message=f"输入的参数 '{map_key}' 不在标准的 tags 中\n是否在找{may_mention_key}?\n如果不是，请输入\n/duel map tags\n查看可映射的 tags")
                            return
                    else:
                        if map_value in tags_map[map_key]:
                            await bot.send(event=event, message=f"当前映射已存在 '{map_key}' - '{map_value}'")
                            return
                        tags_map[map_key].append(map_value)
                        tags_quick_map[map_value] = map_key
                        JsonUtils.update(plugin_config.filename, {
                            "map": tags_map,
                            "quick_map": tags_quick_map
                        })
                        await bot.send(event=event, message=f"映射键值对添加成功：'{map_key}' - '{map_value}'\n可以通过\n/duel map current\n查看")
                        return
                # 当map后面的参数为rm时，实行删除映射的操作
                elif map_opt_params[0] in ['rm', 'remove', '删除']:
                    if len(map_opt_params) == 1:
                        await bot.send(event=eval, message=f"该命令在 rm 后接收两个参数，第一个参数是存在的可映射的 tag ，第二个参数是 tag 的映射。如\"duel map rm 'binary search' 二分\"")
                        return
                    elif len(map_opt_params) != 3:
                        await bot.send(event=event, message=f"参数个数有误！！！\n该命令在 rm 后面只接收两个参数，请检查当前参数：{map_opt_params}\n可以使用命令\n/duel map rm\n查看命令使用详细")
                        return
                    map_key = map_opt_params[1]
                    map_value = map_opt_params[2]
                    if map_key not in tags_map:
                        may_mention_key: list[str] = regex_search(list(tags_map.keys()), map_key)
                        if not may_mention_key:
                            await bot.send(event=event, message=f"输入的参数 '{map_key}' 不在标准的 tags 中，请输入\"/duel map tags\"查看可映射的tags")
                            return
                        else:
                            await bot.send(event=event, message=f"输入的参数 '{map_key}' 不在标准的 tags 中\n是否在找{may_mention_key}?\n如果不是，请输入\"/duel map tags\"查看可映射的tags")
                            return
                    else:
                        if map_value in tags_map[map_key]:
                            tags_map[map_key].remove(map_value)
                            tags_quick_map.pop(map_value)
                            JsonUtils.update(plugin_config.filename, {
                                "map": tags_map,
                                "quick_map": tags_quick_map
                            })
                            await bot.send(event=event, message=f"映射键值对删除成功：'{map_key}' : '{map_value}'")
                            return
                        else:
                            await bot.send(event=event, message=f"当前映射不存在 '{map_key}' : '{map_value}'")
                            return
                else:
                    await bot.send(event=event, message=f"map 后跟了未知参数: {map_opt_params[0]}，请使用\n/duel map\n查看可用的命令")
                    return
        else:
            await bot.send(event=event, message=f"未知命令: {params[0]}")
            return
    except Exception as e:
        logger.opt(exception=True).error(f"[duel]响应错误: {str(e)}")
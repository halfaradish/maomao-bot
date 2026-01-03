"""
群聊禁言插件

用法: @bot ban @成员 60
"""

from __future__ import annotations

import os

import time

from nonebot import get_driver, on_command
from nonebot.adapters.onebot.v11 import Bot, GroupMessageEvent, Message
from nonebot.exception import FinishedException
from nonebot.log import logger
from nonebot.params import CommandArg
from nonebot.plugin import PluginMetadata
from nonebot.rule import Rule

from ...common import JsonUtils

__plugin_meta__ = PluginMetadata(
    name="群聊禁言",
    description="通过白名单控制, 允许指定用户/群组使用禁言功能",
    usage="@bot ban @成员 60",
    type="application",
    supported_adapters={"~onebot.v11"},
)

# 白名单配置文件
WHITELIST_FILENAME = "ban_whitelist.json"
DEFAULT_WHITELIST = {
    "group_whitelist": [],
    "user_whitelist": ["3026754892","434732989"],
}

driver = get_driver()


def _load_whitelist() -> dict:
    data, _ = JsonUtils.read(WHITELIST_FILENAME, DEFAULT_WHITELIST)
    if not isinstance(data, dict):
        return DEFAULT_WHITELIST.copy()
    data.setdefault("group_whitelist", [])
    data.setdefault("user_whitelist", [])
    return data


def _is_allowed(event: GroupMessageEvent) -> bool:
    whitelist = _load_whitelist()
    user_id = str(event.user_id)
    group_id = str(event.group_id)

    if user_id in driver.config.superusers:
        return True
    if user_id in whitelist["user_whitelist"]:
        return True
    if group_id in whitelist["group_whitelist"]:
        return True
    return False


def _extract_target(event: GroupMessageEvent) -> int | None:
    """返回要禁言的用户 QQ 号"""
    for seg in event.get_message():
        if seg.type != "at":
            continue
        qq = seg.data.get("qq")
        if not qq or qq in ("all", str(event.self_id)):
            continue
        try:
            return int(qq)
        except ValueError:
            return None
    return None


def _parse_duration(arg_text: str) -> int | None:
    text = arg_text.strip()
    if not text:
        return None
    # 允许简单单位（s/m/h），默认秒
    factor = 1
    if text[-1].lower() in ("s", "m", "h"):
        unit = text[-1].lower()
        text = text[:-1]
        if unit == "m":
            factor = 60
        elif unit == "h":
            factor = 3600
    if not text.isdigit():
        return None
    seconds = int(text) * factor
    return seconds if seconds > 0 else None


# 定义规则：确保命令是独立的单词（避免误触发，如 banana 不会触发 ban）
def _is_word_boundary_command(cmd: str):
    """确保命令是独立的单词，避免误触发（如 banana 不会触发 ban）"""
    async def _rule(event: GroupMessageEvent) -> bool:
        if not isinstance(event, GroupMessageEvent):
            return False
        # 获取消息文本
        msg_text = event.get_plaintext().strip()
        
        # 检查消息是否以命令开头
        if not msg_text.lower().startswith(cmd.lower()):
            return False
        
        # 如果命令长度等于消息长度，说明是完整匹配
        if len(msg_text) == len(cmd):
            return True
        
        # 检查命令后的字符：必须是空格、标点符号或非字母数字字符
        next_char = msg_text[len(cmd)]
        # 允许的字符：空格、制表符、换行符、@符号、中文标点等
        if next_char in (' ', '\t', '\n', '@', '，', '。', '！', '？', '、', '：', '；'):
            return True
        # 如果是非字母数字字符，也允许（如标点符号）
        if not next_char.isalnum():
            return True
            
        return False
    return Rule(_rule)

ban_cmd = on_command("ban", rule=_is_word_boundary_command("ban"), priority=10, block=True)
unban_cmd = on_command("unban", rule=_is_word_boundary_command("unban"), priority=10, block=True)
kick_cmd = on_command("kick", rule=_is_word_boundary_command("kick"), priority=10, block=True)


@ban_cmd.handle()
async def handle_ban(bot: Bot, event: GroupMessageEvent, args: Message = CommandArg()):
    if not isinstance(event, GroupMessageEvent):
        await ban_cmd.finish("仅支持在群聊中使用禁言功能")
        return

    if not _is_allowed(event):
        await ban_cmd.finish("你没有权限使用禁言功能")
        return

    target_user = _extract_target(event)
    if not target_user:
        await ban_cmd.finish("请 @ 需要禁言的用户")
        return

    # 检查被禁言对象是否为管理员/群主
    try:
        member_info = await bot.get_group_member_info(
            group_id=event.group_id, user_id=target_user, no_cache=True
        )
    except Exception as e:
        logger.error(f"获取成员信息失败: {e}")
        await ban_cmd.finish("无法获取成员信息，禁言已取消")
        return

    role = member_info.get("role")
    if role in ("admin", "owner"):
        await ban_cmd.finish("无法禁言管理员或群主")
        return

    duration = _parse_duration(args.extract_plain_text())
    if duration is None:
        await ban_cmd.finish("请提供禁言时长（数字或带 s/m/h），例如 60、10m")
        return

    try:
        await bot.set_group_ban(group_id=event.group_id, user_id=target_user, duration=duration)

        # 再次获取信息以确认禁言是否生效
        verify_info = await bot.get_group_member_info(
            group_id=event.group_id, user_id=target_user, no_cache=True
        )
        shut_up_timestamp = verify_info.get("shut_up_timestamp", 0)
        if shut_up_timestamp <= time.time():
            await ban_cmd.finish("禁言可能未生效（用户可能为管理员），请人工确认")
            return

        await ban_cmd.finish(f"已禁言 {target_user}，时长 {duration} 秒")
    except FinishedException:
        raise
    except Exception as e:
        logger.error(f"设置禁言失败: {e}")
        await ban_cmd.finish("禁言失败，请检查机器人权限")


@unban_cmd.handle()
async def handle_unban(bot: Bot, event: GroupMessageEvent, args: Message = CommandArg()):
    if not isinstance(event, GroupMessageEvent):
        await unban_cmd.finish("仅支持在群聊中使用禁言功能")
        return

    if not _is_allowed(event):
        await unban_cmd.finish("你没有权限使用解除禁言功能")
        return

    target_user = _extract_target(event)
    if not target_user:
        await unban_cmd.finish("请 @ 需要解除禁言的用户")
        return

    try:
        member_info = await bot.get_group_member_info(
            group_id=event.group_id, user_id=target_user, no_cache=True
        )
    except Exception as e:
        logger.error(f"获取成员信息失败: {e}")
        await unban_cmd.finish("无法获取成员信息，解除禁言已取消")
        return

    shut_up_timestamp = member_info.get("shut_up_timestamp", 0)
    if shut_up_timestamp <= time.time():
        await unban_cmd.finish("该用户当前没有被禁言")
        return

    try:
        await bot.set_group_ban(group_id=event.group_id, user_id=target_user, duration=0)
        await unban_cmd.finish(f"已解除 {target_user} 的禁言")
    except FinishedException:
        raise
    except Exception as e:
        logger.error(f"解除禁言失败: {e}")
        await unban_cmd.finish("解除禁言失败，请检查机器人权限")


async def _bot_can_manage(bot: Bot, group_id: int) -> bool:
    """检查机器人是否为管理员/群主"""
    try:
        info = await bot.get_group_member_info(group_id=group_id, user_id=bot.self_id, no_cache=True)
        return info.get("role") in {"admin", "owner"}
    except Exception as e:
        logger.error(f"获取机器人身份失败: {e}")
        return False


@kick_cmd.handle()
async def handle_kick(bot: Bot, event: GroupMessageEvent, args: Message = CommandArg()):
    if not isinstance(event, GroupMessageEvent):
        await kick_cmd.finish("仅支持在群聊中使用踢人功能")
        return

    if not _is_allowed(event):
        await kick_cmd.finish("你没有权限使用踢人功能")
        return

    if not await _bot_can_manage(bot, event.group_id):
        await kick_cmd.finish("机器人没有管理员权限，无法踢人")
        return

    target_user = _extract_target(event)
    if not target_user:
        await kick_cmd.finish("请 @ 需要踢出的用户")
        return

    if target_user == event.self_id:
        await kick_cmd.finish("不能踢出机器人自己")
        return

    try:
        member_info = await bot.get_group_member_info(
            group_id=event.group_id, user_id=target_user, no_cache=True
        )
    except Exception as e:
        logger.error(f"获取成员信息失败: {e}")
        await kick_cmd.finish("无法获取成员信息，踢人已取消")
        return

    role = member_info.get("role")
    if role in ("admin", "owner"):
        await kick_cmd.finish("无法踢出管理员或群主")
        return

    try:
        await bot.set_group_kick(group_id=event.group_id, user_id=target_user, reject_add_request=False)
        await kick_cmd.finish(f"已将 {target_user} 移出群聊")
    except FinishedException:
        raise
    except Exception as e:
        logger.error(f"踢出成员失败: {e}")
        await kick_cmd.finish("踢出失败，请检查机器人权限")

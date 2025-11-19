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


ban_cmd = on_command("ban", priority=10, block=True)


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


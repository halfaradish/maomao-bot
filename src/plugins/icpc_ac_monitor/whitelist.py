# src/plugins/icpc_ac_monitor/whitelist.py
"""艾特白名单管理辅助：鉴权、序列化/落盘、QQ 解析"""

import re
from typing import Dict, List, Optional

from nonebot.adapters.onebot.v11 import Event, Message

from .state import AT_WHITELIST, conf, save_conf
from src.common.permission import ADMIN_PERM_KEY, check_permission


async def _is_authorized(event: Event) -> bool:
    """管理员或本插件的艾特白名单成员才可管理

    管理员判据是权限点（``perm_admin`` 组），不再是 SUPERUSERS —— 之前这里用
    模块级快照 ``{str(u) for u in config.superusers}`` 加 ``except → set()``，
    配置读取一异常就静默变成「没有任何超级管理员」，且永久拿的是导入瞬间的快照。
    """
    user_id = getattr(event, "user_id", None)
    if user_id is None:
        return False
    if await check_permission(event, ADMIN_PERM_KEY):
        return True
    try:
        uid = int(user_id)
    except Exception:
        return False
    return uid in AT_WHITELIST


def _serialize_whitelist() -> List[Dict[str, Optional[int]]]:
    return [{"qq": qq, "group_id": gid} for qq, gid in AT_WHITELIST.items()]


def _persist_at_whitelist():
    """落盘艾特白名单"""
    conf["at_whitelist"] = _serialize_whitelist()
    save_conf(conf)


def _parse_qq_numbers(text: str) -> List[int]:
    """将输入文本解析为 QQ 号列表"""
    tokens = re.split(r"[\s,，]+", text.strip())
    qq_list = []
    for token in tokens:
        if not token:
            continue
        if not token.isdigit():
            raise ValueError(f"非法 QQ 号：{token}")
        qq_list.append(int(token))
    if not qq_list:
        raise ValueError("未解析到任何 QQ 号")
    return qq_list


def _extract_mentions(message: Message) -> List[int]:
    """从命令参数中解析 @ 的 QQ"""
    mentions: List[int] = []
    for seg in message:
        if seg.type != "at":
            continue
        qq = seg.data.get("qq")
        if not qq or qq == "all" or not str(qq).isdigit():
            continue
        mentions.append(int(qq))
    return mentions

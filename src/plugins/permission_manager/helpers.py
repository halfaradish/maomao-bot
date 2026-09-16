"""子命令参数解析与帮助文本。

全部为纯函数，不依赖匹配器。
"""
from dataclasses import dataclass
from typing import List, Optional

from nonebot.adapters.onebot.v11 import Message


@dataclass
class ArgToken:
    kind: str  # "text" | "at"
    value: str


def _tokenize_arguments(message: Message) -> List[ArgToken]:
    """将消息拆分为 token 列表（at / text）"""
    tokens: List[ArgToken] = []
    for seg in message:
        if seg.type == "text":
            text = seg.data.get("text", "")
            for part in text.replace("\n", " ").split():
                if part:
                    tokens.append(ArgToken("text", part))
        elif seg.type == "at":
            qq = seg.data.get("qq")
            if qq and qq not in ("all", "0"):
                tokens.append(ArgToken("at", qq))
    return tokens


def _try_parse_qq(token: ArgToken) -> Optional[int]:
    """尝试从 token 解析 QQ 号（at 或纯数字）"""
    if token.kind == "at" and token.value.isdigit():
        return int(token.value)
    if token.kind == "text":
        text = token.value.lstrip("@")
        if text.isdigit():
            return int(text)
    return None


def _build_help_text() -> str:
    return (
        "perm 命令可用操作（也支持中文）:\n"
        "━━━ 黑名单/blacklist ━━━\n"
        "perm 黑名单 添加/add <QQ号> [原因]\n"
        "perm 黑名单 移除/remove <QQ号>\n"
        "perm 黑名单 列表/list\n"
        "━━━ 白名单/whitelist ━━━\n"
        "perm 白名单 用户/user 添加/add <QQ号> [原因]\n"
        "perm 白名单 用户/user 移除/remove <QQ号>\n"
        "perm 白名单 用户/user 列表/list\n"
        "perm 白名单 群/group 添加/add <群号> [原因]\n"
        "perm 白名单 群/group 移除/remove <群号>\n"
        "perm 白名单 群/group 列表/list\n"
        "━━━ 权限组/group ━━━\n"
        "perm 权限组 创建/create <名称> [展示名] [描述]\n"
        "perm 权限组 删除/delete <名称>\n"
        "perm 权限组 列表/list\n"
        "perm 权限组 详情/info <名称>\n"
        "perm 权限组 添加成员/addmember <名称> <QQ> [QQ...]\n"
        "perm 权限组 移除成员/removemember <名称> <QQ>\n"
        "perm 权限组 添加权限/addperm <名称> <perm_key> [perm_key...]\n"
        "perm 权限组 移除权限/removeperm <名称> <perm_key>\n"
        "perm 权限组 批量加群/batchaddgroup <名称> <群号>\n"
        "━━━ 群绑定/bind ━━━\n"
        "perm 绑定 群/group <群号> <权限组名>\n"
        "perm 绑定 解除/unbind <群号>\n"
        "perm 绑定 列表/list [群号]\n"
        "━━━ 其他 ━━━\n"
        "perm 注册点/points 列表/list [插件名]\n"
        "perm 查看/view <QQ号>\n"
        "perm 登录/login - 获取Web管理面板登录验证码"
    )

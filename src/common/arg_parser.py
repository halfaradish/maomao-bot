"""命令参数分词：把 OneBot v11 消息拆成 ``text`` / ``at`` token，并按需解析出 QQ 号。

``permission_manager`` 与 ``group_manager`` 原先各有一份逐字重复的实现，现合并到这里的
一份。约定（改动时请保持）：
  - ``text`` 段先按空白分词，换行视作空格；
  - ``at`` 段取 ``qq`` 属性，跳过空值以及 ``all`` / ``0``；
  - ``try_parse_qq`` 只认纯数字，``text`` 形式允许带一个前缀 ``@``。

纯函数：不依赖匹配器、数据库或配置，也不做任何 I/O。
"""
from dataclasses import dataclass
from typing import List, Optional

from nonebot.adapters.onebot.v11 import Message


@dataclass
class ArgToken:
    kind: str  # "text" | "at"
    value: str


def tokenize_arguments(message: Message) -> List[ArgToken]:
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


def try_parse_qq(token: ArgToken) -> Optional[int]:
    """尝试从 token 解析 QQ 号（at 或纯数字）"""
    if token.kind == "at" and token.value.isdigit():
        return int(token.value)
    if token.kind == "text":
        text = token.value.lstrip("@")
        if text.isdigit():
            return int(text)
    return None

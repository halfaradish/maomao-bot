from nonebot import logger
from nonebot.adapters.onebot.v11 import Message, MessageSegment
from typing import List, Optional
import re

from ...common.send_forward_msg import SenderInfo
from ...common.json_utils import JsonUtils
from .config import config
from . import utils


MESSAGE_SEPARATOR = config.fakemsg_user_split


def process_command(raw_message: str, user_id: str) -> Optional[str]:
    """
    处理用户管理命令：返回处理结果消息（None表示未处理命令）
    """
    person_users, _, _ = utils.get_plugin_config()
    person_users = [str(person) for person in person_users]
    if str(user_id) not in person_users:
        logger.info(f"{user_id}没有权限使用增删查命令")
        return None

    add_pattern = r"(?:^|\b|\s)-add\s+(\d{6,10})(?!\d)"
    rm_pattern = r"(?:^|\b|\s)-rm\s+(\d{6,10})(?!\d)"
    ls_pattern = r"(?:^|\b|\s)(-ls|-list)\b"

    if re.search(ls_pattern, raw_message):
        if not person_users:
            return "当前person_users列表为空"
        return "当前person_users列表：\n" + "\n".join(f"• {qq}" for qq in sorted(person_users))

    if add_match := re.search(add_pattern, raw_message):
        qq_number = add_match.group(1)
        if qq_number in person_users:
            return f"QQ {qq_number} 已在person_users列表中"
        person_users.append(qq_number)
        JsonUtils.update("fakemsg.json", updates={"person_users": person_users})
        return f"已添加 QQ {qq_number} 到person_users列表"

    if rm_match := re.search(rm_pattern, raw_message):
        qq_number = rm_match.group(1)
        if qq_number not in person_users:
            return f"QQ {qq_number} 不在person_users列表中"
        person_users.remove(qq_number)
        JsonUtils.update("fakemsg.json", updates={"person_users": person_users})
        return f"已移除 QQ {qq_number} 从person_users列表"

    logger.info("无匹配命令")
    return "无匹配命令"


def extract_fake_messages(message: Message) -> List[SenderInfo]:
    """
    从 message 中提取伪造消息。
    """
    if not message:
        return []

    segs = list(message)
    result: List[SenderInfo] = []
    i = 0

    while i < len(segs):
        qq: Optional[str] = None

        if (
            segs[i].type == "at"
            and i + 1 < len(segs)
            and segs[i + 1].type == "text"
        ):
            at_qq = str(segs[i].data.get("qq", ""))
            text = segs[i + 1].data.get("text", "")
            m = re.match(r'^(\s*)说([\s\S]*)$', text)
            if m:
                qq = at_qq
                prefix_len = len(m.group(1)) + 1
                segs[i + 1] = MessageSegment.text(text[prefix_len:])
                i += 1

        elif segs[i].type == "text":
            text = segs[i].data.get("text", "")
            m = re.search(r'(\d{6,10})\s*说', text)
            if m:
                qq = m.group(1)
                segs[i] = MessageSegment.text(text[m.end():])

        if qq is not None:
            content: List[MessageSegment] = []

            while i < len(segs):
                seg = segs[i]

                if seg.type == "text":
                    text = seg.data.get("text", "")

                    if MESSAGE_SEPARATOR in text:
                        idx = text.index(MESSAGE_SEPARATOR)
                        if idx > 0:
                            content.append(MessageSegment.text(text[:idx]))

                        result.append(SenderInfo(user_id=qq, nickname=None, message=Message(content) if content else Message()))

                        after = text[idx + 1:]
                        if after:
                            segs[i] = MessageSegment.text(after)
                        else:
                            i += 1
                        break

                    else:
                        content.append(seg)
                        i += 1

                else:
                    content.append(seg)
                    i += 1

            else:
                result.append(SenderInfo(user_id=qq, nickname=None, message=Message(content) if content else Message()))

        else:
            i += 1

    return result

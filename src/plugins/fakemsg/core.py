from nonebot import logger
from nonebot.adapters.onebot.v11 import Message, MessageSegment, GroupMessageEvent
from typing import List, Optional
import re
from sqlalchemy import select

from ...common.send_forward_msg import SenderInfo
from ...common.permission import check_permission
from ...common.permission.cache import perm_cache
from ...common.database import async_session_factory
from ...common.permission.models import (
    PermissionGroup,
    PermissionGroupMember,
    PermissionGroupPerm,
)
from .config import config


MESSAGE_SEPARATOR = config.fakemsg_user_split

# 默认权限组名，-add/-rm/-ls 命令操作此组的成员
DEFAULT_PG_NAME = "fakemsg_users"


async def process_command(event: GroupMessageEvent) -> Optional[str]:
    """
    处理用户管理命令：返回处理结果消息（None表示未处理命令）
    需要 fakemsg:manage 权限。
    """
    if not await check_permission(event, "fakemsg:manage"):
        logger.info(f"{event.user_id}没有权限使用增删查命令")
        return None

    raw_message = event.raw_message

    add_pattern = r"(?:^|\b|\s)-add\s+(\d{6,10})(?!\d)"
    rm_pattern = r"(?:^|\b|\s)-rm\s+(\d{6,10})(?!\d)"
    ls_pattern = r"(?:^|\b|\s)(-ls|-list)\b"

    if re.search(ls_pattern, raw_message):
        async with async_session_factory() as session:
            result = await session.execute(
                select(PermissionGroup).where(PermissionGroup.name == DEFAULT_PG_NAME).limit(1)
            )
            pg = result.scalars().first()
            if not pg:
                return "当前伪消息白名单为空"
            result = await session.execute(
                select(PermissionGroupMember.user_id)
                .where(PermissionGroupMember.group_id == pg.id)
                .order_by(PermissionGroupMember.user_id)
            )
            user_ids = [str(row[0]) for row in result.all()]
            if not user_ids:
                return "当前伪消息白名单为空"
            return "当前伪消息白名单：\n" + "\n".join(f"• {qq}" for qq in user_ids)

    if add_match := re.search(add_pattern, raw_message):
        qq_number = add_match.group(1)
        async with async_session_factory() as session:
            # 确保权限组存在
            result = await session.execute(
                select(PermissionGroup).where(PermissionGroup.name == DEFAULT_PG_NAME).limit(1)
            )
            pg = result.scalars().first()
            if not pg:
                pg = PermissionGroup(
                    name=DEFAULT_PG_NAME,
                    display_name="伪消息白名单",
                    description="自动创建：伪消息无限制使用及管理权限组",
                    created_by=event.user_id,
                )
                session.add(pg)
                await session.flush()
                session.add(PermissionGroupPerm(group_id=pg.id, perm_key="fakemsg:use"))
                session.add(PermissionGroupPerm(group_id=pg.id, perm_key="fakemsg:manage"))

            # 检查是否已是成员
            existing = await session.execute(
                select(PermissionGroupMember.id).where(
                    PermissionGroupMember.group_id == pg.id,
                    PermissionGroupMember.user_id == int(qq_number),
                ).limit(1)
            )
            if existing.first() is not None:
                return f"QQ {qq_number} 已在伪消息白名单中"

            session.add(PermissionGroupMember(group_id=pg.id, user_id=int(qq_number)))
            await session.commit()

            # 清除该用户的权限缓存
            perm_cache.clear_pattern(f"perm:{qq_number}:")
            return f"已添加 QQ {qq_number} 到伪消息白名单"

    if rm_match := re.search(rm_pattern, raw_message):
        qq_number = rm_match.group(1)
        async with async_session_factory() as session:
            result = await session.execute(
                select(PermissionGroup).where(PermissionGroup.name == DEFAULT_PG_NAME).limit(1)
            )
            pg = result.scalars().first()
            if not pg:
                return f"QQ {qq_number} 不在伪消息白名单中"

            result = await session.execute(
                select(PermissionGroupMember).where(
                    PermissionGroupMember.group_id == pg.id,
                    PermissionGroupMember.user_id == int(qq_number),
                )
            )
            members = result.scalars().all()
            if not members:
                return f"QQ {qq_number} 不在伪消息白名单中"

            for member in members:
                await session.delete(member)
            await session.commit()

            # 清除该用户的权限缓存
            perm_cache.clear_pattern(f"perm:{qq_number}:")
            return f"已移除 QQ {qq_number} 从伪消息白名单"

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

"""
Handlers for ACK/ANN commands and reaction tracking.
"""
from __future__ import annotations

import re
from typing import Any, Dict, List, Optional, Tuple

from nonebot import on_notice, on_regex
from nonebot.adapters.onebot.v11 import Bot, Event, GroupMessageEvent, NoticeEvent, MessageSegment
from nonebot.adapters.onebot.v11.exception import ActionFailed
from nonebot.log import logger
from nonebot.params import RegexGroup

from . import database


def _normalize_whitespace(text: str) -> str:
    return re.sub(r"\s+", " ", text).strip()


ack_command = on_regex(r"^!ACK\s+(.+)", flags=re.IGNORECASE, priority=8, block=True)
ann_command = on_regex(r"^!ANN\s+(.+)", flags=re.IGNORECASE, priority=8, block=True)
reaction_notice = on_notice(priority=50, block=False)


@ack_command.handle()
async def handle_ack_command(
    bot: Bot,
    event: Event,
    groups: Tuple[str, ...] = RegexGroup(),
):
    if not isinstance(event, GroupMessageEvent):
        await ack_command.finish("全员确认指令目前仅支持群聊使用。")

    content = _normalize_whitespace(groups[0] if groups else "")
    if not content:
        await ack_command.finish("请在 !ACK 指令后提供需要公告的内容。")

    group_id = event.group_id
    command_sender = event.user_id
    bot_uin = int(bot.self_id)

    try:
        members_raw = await bot.get_group_member_list(group_id=group_id)
    except Exception as exc:
        logger.warning("获取群成员列表失败: %s", exc)
        members_raw = []

    member_snapshot: List[Dict[str, Any]] = []
    for info in members_raw:
        user_id = info.get("user_id")
        if user_id is None:
            continue
        try:
            user_int = int(user_id)
        except Exception:
            continue
        if user_int == bot_uin:
            continue
        member_snapshot.append(
            {
                "uin": user_int,
                "nickname": info.get("card") or info.get("nickname"),
                "role": info.get("role"),
            }
        )

    ack_text = "[全员确认]\n{}\n请通过任意表情确认收到。".format(content)

    # 尝试@全体成员（如果有权限）
    try:
        at_all_message = MessageSegment.at("all") + "\n" + ack_text
        send_result = await bot.send_group_msg(group_id=group_id, message=at_all_message)
    except ActionFailed:
        # 权限不足，降级为普通消息
        logger.debug("Bot无@全体权限，发送普通消息")
        send_result = await bot.send_group_msg(group_id=group_id, message=ack_text)
    except Exception as exc:
        # 其他错误，也降级为普通消息
        logger.warning("发送@全体消息失败，降级为普通消息: %s", exc)
        send_result = await bot.send_group_msg(group_id=group_id, message=ack_text)
    raw_msg_id = send_result.get("message_id")
    msg_id = str(raw_msg_id) if raw_msg_id is not None else None
    msg_seq: Optional[int] = None
    message_detail: Dict[str, Any] = {}
    if raw_msg_id is not None:
        try:
            detail = await bot.get_msg(message_id=raw_msg_id)
            message_detail = detail or {}
            seq_value = detail.get("message_seq") or detail.get("seq")
            if seq_value is not None:
                try:
                    msg_seq = int(seq_value)
                except Exception:
                    msg_seq = None
        except Exception as exc:
            logger.debug("获取消息详情失败: %s", exc)

    metadata = {
        "command_sender": command_sender,
        "command_event_id": event.message_id,
        "command_content": event.get_plaintext(),
        "message_detail": message_detail,
    }

    await database.create_ack_message_record(
        bot_uin=bot_uin,
        scene_type="group",
        content=ack_text,
        target_members=member_snapshot,
        group_id=group_id,
        msg_seq=msg_seq,
        msg_id=msg_id,
        metadata=metadata,
    )


@ann_command.handle()
async def handle_ann_command(
    bot: Bot,
    event: Event,
    groups: Tuple[str, ...] = RegexGroup(),
):
    if not isinstance(event, GroupMessageEvent):
        await ann_command.finish("公告指令目前仅支持群聊使用。")

    content = _normalize_whitespace(groups[0] if groups else "")
    if not content:
        await ann_command.finish("请在 !ANN 指令后提供公告内容。")

    group_id = event.group_id
    ann_text = "[公告]\n{}".format(content)
    await bot.send_group_msg(group_id=group_id, message=ann_text)
    await ann_command.finish("公告已发送。")


@reaction_notice.handle()
async def handle_reaction_notice(bot: Bot, event: NoticeEvent):
    # 尝试多种方式获取 notice_type
    event_dict = event.dict()
    notice_type = (
        getattr(event, "notice_type", None)
        or event_dict.get("notice_type")
        or getattr(event, "sub_type", None)
        or event_dict.get("sub_type")
    )
    
    # 支持多种可能的事件类型名称（不同 OneBot 实现可能不同）
    valid_notice_types = {
        "group_msg_reactions",
        "group_msg_reaction",  # 单数形式
        "message_reaction",    # 通用形式
        "message_reactions",   # 通用复数形式
    }
    
    # 先提取事件信息，用于判断是否是表情反应事件
    msg_id = (
        event_dict.get("message_id")
        or event_dict.get("msg_id")
        or getattr(event, "message_id", None)
        or getattr(event, "msg_id", None)
    )
    reactor = (
        event_dict.get("user_id")
        or event_dict.get("operator_id")
        or event_dict.get("reactor_uin")
        or getattr(event, "user_id", None)
        or getattr(event, "operator_id", None)
    )
    reaction_type = (
        event_dict.get("reaction_type")
        or event_dict.get("emoji_id")
        or event_dict.get("emoji")
    )
    
    # 判断是否是表情反应事件：
    # 1. notice_type 在有效列表中，或
    # 2. 事件包含消息ID和用户ID（可能是表情反应事件）
    is_reaction_event = (
        notice_type in valid_notice_types
        or (msg_id is not None and reactor is not None)
    )
    
    if not is_reaction_event:
        # 记录其他类型的通知事件，帮助排查问题（使用 info 级别以便调试）
        logger.info(
            "收到非表情反应通知事件: notice_type=%s, event_type=%s, event_dict_keys=%s, event_dict=%s",
            notice_type, type(event).__name__, list(event_dict.keys()), event_dict
        )
        return
    
    # 如果 notice_type 不在列表中，但事件包含表情反应相关字段，记录日志
    if notice_type not in valid_notice_types:
        logger.info(
            "通过字段检测到表情反应事件: notice_type=%s, msg_id=%s, reactor=%s, reaction_type=%s, event_dict=%s",
            notice_type, msg_id, reactor, reaction_type, event_dict
        )

    # 继续提取其他事件信息（尝试多种可能的字段名）
    msg_seq = (
        event_dict.get("message_seq")
        or event_dict.get("msg_seq")
        or getattr(event, "message_seq", None)
        or getattr(event, "msg_seq", None)
    )
    group_id = (
        event_dict.get("group_id")
        or getattr(event, "group_id", None)
    )
    
    # 增强日志：记录收到的表情反应事件详情
    logger.info(
        "收到表情反应事件: notice_type=%s, msg_id=%s, msg_seq=%s, group_id=%s, reactor=%s, event_dict=%s",
        notice_type, msg_id, msg_seq, group_id, reactor, event_dict
    )
    
    if reactor is None:
        logger.warning("表情反应事件缺少reactor信息: %s", event_dict)
        return

    reactor_uin = None
    try:
        reactor_uin = int(reactor)
    except Exception:
        logger.warning("表情反应事件reactor不是整数: %s", reactor)
        return

    action = event_dict.get("action") or event_dict.get("sub_type")
    is_remove = False
    if isinstance(action, str):
        is_remove = action.lower() in {"remove", "delete", "cancel", "unset"}
    elif isinstance(action, int):
        is_remove = action in {0, 2}

    # 如果之前没有提取到 reaction_type，再次尝试提取
    if not reaction_type:
        reaction_type = (
            event_dict.get("reaction_type")
            or event_dict.get("emoji_id")
            or event_dict.get("emoji")
            or "unknown"
        )

    identifier = {
        "msg_id": msg_id,
        "msg_seq": msg_seq,
        "group_id": group_id,
    }

    logger.info(
        "处理表情反应: identifier=%s, reactor_uin=%s, reaction_type=%s, is_remove=%s",
        identifier, reactor_uin, reaction_type, is_remove
    )

    if is_remove:
        result = await database.remove_reaction(identifier, reactor_uin)
    else:
        result = await database.record_reaction(
            identifier, reactor_uin, str(reaction_type), event_dict
        )

    if not result:
        logger.warning(
            "表情反应处理失败，未找到对应消息: identifier=%s, reactor_uin=%s",
            identifier, reactor_uin
        )
        return

    completed, outstanding, status_changed, _ = result
    logger.info(
        "表情反应处理完成: completed=%s, outstanding_count=%s, status_changed=%s, outstanding=%s",
        completed, len(outstanding), status_changed, outstanding
    )
    
    if completed and status_changed and group_id:
        try:
            await bot.send_group_msg(
                group_id=int(group_id),
                message="[全员确认] 已收到全部表情确认，感谢配合。",
            )
        except Exception as exc:
            logger.warning("发送完成通知失败: %s", exc)
    elif not completed:
        logger.info(
            "全员确认进行中: identifier=%s, 剩余成员数=%s, 剩余成员=%s",
            identifier,
            len(outstanding),
            outstanding,
        )


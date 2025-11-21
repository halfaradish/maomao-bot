"""
Handlers for ACK/ANN commands and reaction tracking.
"""
from __future__ import annotations

import re
from typing import Any, Dict, List, Optional, Tuple

from nonebot import on_notice, on_regex
from nonebot.adapters.onebot.v11 import (
    Bot,
    Event,
    GroupMessageEvent,
    Message,
    MessageSegment,
    NoticeEvent,
)
from nonebot.adapters.onebot.v11.exception import ActionFailed
from nonebot.log import logger
from nonebot.params import RegexGroup

from . import database


def _normalize_whitespace(text: str) -> str:
    return re.sub(r"\s+", " ", text).strip()


CQ_AT_PATTERN = re.compile(r"\[CQ:at,qq=[^\]]+\]")
GROUP_MARKER_PATTERN = re.compile(r"@([\u4e00-\u9fa5A-Za-z0-9_\-]+)")


def _strip_cq_at_segments(text: str) -> str:
    """移除消息中的CQ at片段文本，避免重复@"""
    return CQ_AT_PATTERN.sub("", text)


def _strip_group_markers(text: str) -> Tuple[str, List[str]]:
    """
    提取文本中的 @分组 标记并移除，返回 (新的文本, 分组名列表)
    """
    group_names: List[str] = []

    def _replacer(match: re.Match) -> str:
        group_name = match.group(1).strip()
        if group_name:
            group_names.append(group_name)
        return " "

    stripped = GROUP_MARKER_PATTERN.sub(_replacer, text)
    return stripped, group_names


def _extract_target_user_ids(event: GroupMessageEvent, bot_uin: int) -> List[int]:
    """从消息中提取被@的成员（排除@全体/机器人自身）"""
    target_ids: List[int] = []
    seen: set[int] = set()
    for segment in event.get_message():
        if segment.type != "at":
            continue
        qq = segment.data.get("qq")
        if not qq or qq in {"all", "here"}:
            continue
        try:
            user_id = int(qq)
        except Exception:
            continue
        if user_id == bot_uin or user_id in seen:
            continue
        seen.add(user_id)
        target_ids.append(user_id)
    return target_ids


def _merge_unique_sequences(*sequences: List[int]) -> List[int]:
    merged: List[int] = []
    seen: set[int] = set()
    for seq in sequences:
        for item in seq:
            if item not in seen:
                seen.add(item)
                merged.append(item)
    return merged


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

    raw_content = groups[0] if groups else ""
    stripped_cq = _strip_cq_at_segments(raw_content)
    content_without_groups, group_mentions = _strip_group_markers(stripped_cq)
    content = _normalize_whitespace(content_without_groups)
    if not content:
        await ack_command.finish("请在 !ACK 指令后提供需要公告的内容。")

    group_id = event.group_id
    command_sender = event.user_id
    bot_uin = int(bot.self_id)
    target_user_ids: List[int] = _extract_target_user_ids(event, bot_uin)
    had_direct_mentions = bool(target_user_ids)

    # 去重并保持顺序
    unique_group_names: List[str] = []
    seen_groups: set[str] = set()
    for name in group_mentions:
        norm = name.strip()
        if not norm or norm in seen_groups:
            continue
        seen_groups.add(norm)
        unique_group_names.append(norm)

    try:
        members_raw = await bot.get_group_member_list(group_id=group_id)
    except Exception as exc:
        logger.warning("获取群成员列表失败: %s", exc)
        members_raw = []

    member_snapshot_all: List[Dict[str, Any]] = []
    members_by_uin: Dict[int, Dict[str, Any]] = {}
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
        entry = {
            "uin": user_int,
            "nickname": info.get("card") or info.get("nickname"),
            "role": info.get("role"),
        }
        member_snapshot_all.append(entry)
        members_by_uin[user_int] = entry

    group_target_ids: List[int] = []
    invalid_groups: List[str] = []
    empty_groups: List[str] = []
    not_in_current_group: Dict[str, List[str]] = {}

    if unique_group_names:
        group_records = await database.get_groups_with_members(unique_group_names)
        for name in unique_group_names:
            record = group_records.get(name)
            if not record:
                invalid_groups.append(name)
                continue
            members = record.get("members", [])
            if not members:
                empty_groups.append(name)
                continue
            valid_count = 0
            for member in members:
                uin = int(member["qq_id"])
                if uin not in members_by_uin:
                    not_in_current_group.setdefault(name, []).append(str(uin))
                    continue
                if uin not in group_target_ids:
                    group_target_ids.append(uin)
                valid_count += 1
            if valid_count == 0:
                empty_groups.append(name)

    target_user_ids = _merge_unique_sequences(target_user_ids, group_target_ids)

    notice_messages: List[str] = []
    if invalid_groups:
        notice_messages.append(f"未找到分组: {', '.join(invalid_groups)}")
    if empty_groups:
        notice_messages.append(f"这些分组在当前群无有效成员: {', '.join(empty_groups)}")
    if not_in_current_group:
        details = []
        for name, members in not_in_current_group.items():
            details.append(f"{name}({', '.join(members)})")
        notice_messages.append(f"以下成员不在当前群: {'; '.join(details)}")
    notice_text = "提示：" + "；".join(notice_messages) if notice_messages else ""

    if not target_user_ids and unique_group_names and not had_direct_mentions:
        message = notice_text or "未找到可用的分组成员，请检查分组名称。"
        await ack_command.finish(message)

    if notice_text and target_user_ids:
        await ack_command.send(notice_text)

    if target_user_ids:
        target_members: List[Dict[str, Any]] = []
        for user_id in target_user_ids:
            member_info = members_by_uin.get(user_id)
            if member_info is None:
                member_info = {"uin": user_id, "nickname": None, "role": None}
            target_members.append(member_info)
        if not target_members:
            # 所有@成员均无效，回退到全体
            target_user_ids = []
            target_members = member_snapshot_all
    else:
        target_members = member_snapshot_all

    ack_text = "{}\n请通过任意表情确认收到。".format(content)

    if target_user_ids:
        targeted_message = Message(
            [MessageSegment.at(user_id) for user_id in target_user_ids]
            + [MessageSegment.text("\n" + ack_text)]
        )
        try:
            send_result = await bot.send_group_msg(group_id=group_id, message=targeted_message)
        except Exception as exc:
            logger.warning("发送定向确认消息失败，降级为普通消息: %s", exc)
            send_result = await bot.send_group_msg(group_id=group_id, message=ack_text)
    else:
        # 尝试@全体成员（如果有权限）
        try:
            at_all_message = Message([MessageSegment.at("all"), MessageSegment.text("\n" + ack_text)])
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
        "target_user_ids": target_user_ids,
        "target_scope": "custom" if target_user_ids else "all",
        "target_group_names": unique_group_names,
        "group_notice": notice_messages,
    }

    await database.create_ack_message_record(
        bot_uin=bot_uin,
        scene_type="group",
        content=ack_text,
        target_members=target_members,
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
                message="[全员确认]已收到全部表情确认，感谢配合。",
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


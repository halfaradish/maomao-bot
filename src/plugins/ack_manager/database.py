"""
Database helpers for ACK/ANN message tracking.
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional, Tuple

from asgiref.sync import sync_to_async
from nonebot.log import logger

from ...common.django_crud import (
    async_create_record,
    async_delete_records,
    async_get_many,
    async_get_one,
    async_update_records,
    init_django_if_needed,
)

init_django_if_needed()

from botdb.models import (
    QQMessageReaction,
    QQMessageReceiptSummary,
    QQRobotMessage,
    beijing_now,
)

TrackedMessageIdentifier = Dict[str, Any]


def _coerce_int(value: Any) -> Optional[int]:
    if value is None:
        return None
    if isinstance(value, int):
        return value
    if isinstance(value, str):
        value = value.strip()
        if value.isdigit():
            try:
                return int(value)
            except ValueError:
                return None
    try:
        return int(value)
    except Exception:
        return None


def _extract_uin_set(target_members: Any) -> List[int]:
    uins: List[int] = []
    if not target_members:
        return uins
    if isinstance(target_members, list):
        for item in target_members:
            candidate: Optional[int] = None
            if isinstance(item, dict):
                candidate = (
                    _coerce_int(item.get("uin"))
                    or _coerce_int(item.get("user_id"))
                    or _coerce_int(item.get("qq"))
                )
            else:
                candidate = _coerce_int(item)
            if candidate is not None:
                uins.append(candidate)
    return uins


async def create_ack_message_record(
    *,
    bot_uin: int,
    scene_type: str,
    content: str,
    target_members: List[Dict[str, Any]],
    group_id: Optional[int] = None,
    guild_id: Optional[str] = None,
    channel_id: Optional[str] = None,
    msg_seq: Optional[int] = None,
    msg_id: Optional[str] = None,
    attachment: Optional[Dict[str, Any]] = None,
    remind_rule: Optional[Dict[str, Any]] = None,
    metadata: Optional[Dict[str, Any]] = None,
    sent_at=None,
) -> QQRobotMessage:
    sent_at = sent_at or beijing_now()
    attachment = attachment or {}
    metadata = metadata or {}

    message = await async_create_record(
        QQRobotMessage,
        bot_uin=bot_uin,
        scene_type=scene_type,
        group_id=group_id,
        guild_id=guild_id,
        channel_id=channel_id,
        msg_seq=msg_seq,
        msg_id=str(msg_id) if msg_id is not None else None,
        content=content,
        attachment=attachment,
        target_members=target_members,
        sent_at=sent_at,
        remind_rule=remind_rule,
        metadata=metadata,
    )

    member_uins = _extract_uin_set(target_members)
    outstanding_members = member_uins.copy()

    # 设置第一次提醒时间：5分钟后（如果配置了提醒间隔）
    from datetime import timedelta
    next_reminder_at = None
    if len(member_uins) > 0:  # 只有在有目标成员时才设置提醒
        # 第一次提醒在5分钟后
        next_reminder_at = sent_at + timedelta(minutes=5)

    await async_create_record(
        QQMessageReceiptSummary,
        message_id=message.id,
        expected_count=len(member_uins),
        confirmed_count=0,
        outstanding_members=outstanding_members,
        last_checked_at=None,
        reminder_stage=0,
        next_reminder_at=next_reminder_at,
    )

    return message


async def _resolve_message(identifier: TrackedMessageIdentifier) -> Optional[QQRobotMessage]:
    msg_id_raw = identifier.get("msg_id")
    # 确保 msg_id 始终转换为字符串，支持整数和字符串两种格式
    msg_id = None
    if msg_id_raw is not None:
        if isinstance(msg_id_raw, (int, float)):
            msg_id = str(int(msg_id_raw))
        else:
            msg_id = str(msg_id_raw).strip()
            if not msg_id:
                msg_id = None
    
    msg_seq = _coerce_int(identifier.get("msg_seq"))
    group_id = _coerce_int(identifier.get("group_id"))
    guild_id = identifier.get("guild_id")
    channel_id = identifier.get("channel_id")

    logger.info(
        "尝试解析消息: identifier=%s, msg_id=%s (type=%s, raw=%s), msg_seq=%s, group_id=%s",
        identifier, msg_id, type(msg_id_raw).__name__ if msg_id_raw else None, msg_id_raw, msg_seq, group_id
    )

    # 首先尝试通过 msg_id 匹配（最准确）
    if msg_id:
        # 尝试精确匹配
        record = await async_get_one(QQRobotMessage, msg_id=msg_id)
        if record:
            logger.info("通过msg_id找到消息: msg_id=%s, record_id=%s, record.msg_id=%s", msg_id, record.id, record.msg_id)
            return record
        else:
            logger.debug("通过msg_id未找到消息: msg_id=%s，尝试其他匹配方式", msg_id)
            # 如果精确匹配失败，尝试查询所有相关消息以便调试
            if group_id:
                all_records = await async_get_many(QQRobotMessage, filters={"group_id": group_id})
                logger.debug(
                    "群组 %s 中的消息记录: 共 %s 条, msg_ids=%s",
                    group_id, len(all_records), [r.msg_id for r in all_records[:10]]
                )
    
    # 如果 msg_id 匹配失败，尝试通过 msg_seq + group_id 匹配
    if msg_seq is not None and group_id is not None:
        record = await async_get_one(QQRobotMessage, msg_seq=msg_seq, group_id=group_id)
        if record:
            logger.info("通过msg_seq+group_id找到消息: msg_seq=%s, group_id=%s, record_id=%s, record.msg_id=%s", 
                       msg_seq, group_id, record.id, record.msg_id)
            # 如果找到了记录但 msg_id 不匹配，更新 msg_id（可能是消息ID格式不一致）
            if record.msg_id != msg_id and msg_id:
                logger.info("发现msg_id不一致，更新记录: record.msg_id=%s -> %s", record.msg_id, msg_id)
                await async_update_records(
                    QQRobotMessage,
                    {"id": record.id},
                    {"msg_id": msg_id}
                )
                record.msg_id = msg_id
            return record
        else:
            logger.debug("通过msg_seq+group_id未找到消息: msg_seq=%s, group_id=%s", msg_seq, group_id)
    
    # 最后尝试通过 guild_id + channel_id 匹配（频道消息）
    if guild_id and channel_id:
        record = await async_get_one(
            QQRobotMessage,
            guild_id=str(guild_id),
            channel_id=str(channel_id),
            msg_id=str(msg_id) if msg_id else None,
        )
        if record:
            logger.info("通过guild_id+channel_id找到消息: guild_id=%s, channel_id=%s, record_id=%s", guild_id, channel_id, record.id)
            return record
    
    logger.warning("无法解析消息: identifier=%s, msg_id=%s, msg_seq=%s, group_id=%s", identifier, msg_id, msg_seq, group_id)
    return None


async def _recompute_summary(
    message: QQRobotMessage,
) -> Tuple[bool, List[int], bool, str]:
    target_uins = set(_extract_uin_set(message.target_members))
    reactions = await async_get_many(
        QQMessageReaction, filters={"message_id": message.id}
    )
    confirmed_uins = {r.reactor_uin for r in reactions if r.reactor_uin is not None}
    confirmed_subset = confirmed_uins & target_uins if target_uins else confirmed_uins
    outstanding = sorted(list(target_uins - confirmed_subset))

    summary = await async_get_one(QQMessageReceiptSummary, message_id=message.id)
    now = beijing_now()
    expected_count = summary.expected_count if summary else len(target_uins)
    if not expected_count:
        expected_count = len(target_uins)

    confirmed_count = len(confirmed_subset)
    
    logger.info(
        "重新计算汇总: message_id=%s, target_count=%s, reactions_count=%s, confirmed_count=%s, outstanding_count=%s",
        message.id, len(target_uins), len(reactions), len(confirmed_subset), len(outstanding)
    )
    
    if summary:
        logger.info(
            "更新汇总记录: message_id=%s, expected_count=%s -> %s, confirmed_count=%s -> %s, outstanding_count=%s -> %s",
            message.id,
            summary.expected_count, expected_count,
            summary.confirmed_count, confirmed_count,
            len(summary.outstanding_members or []), len(outstanding)
        )
        await async_update_records(
            QQMessageReceiptSummary,
            {"message_id": message.id},
            {
                "expected_count": expected_count,
                "confirmed_count": confirmed_count,
                "outstanding_members": outstanding,
                "last_checked_at": now,
            },
        )
    else:
        logger.info(
            "创建新汇总记录: message_id=%s, expected_count=%s, confirmed_count=%s, outstanding_count=%s",
            message.id, expected_count, confirmed_count, len(outstanding)
        )
        await async_create_record(
            QQMessageReceiptSummary,
            message_id=message.id,
            expected_count=expected_count,
            confirmed_count=confirmed_count,
            outstanding_members=outstanding,
            last_checked_at=now,
        )

    completed = bool(expected_count) and not outstanding
    previous_status = message.status
    new_status = previous_status
    status_changed = False

    if completed and previous_status != QQRobotMessage.MessageStatus.CLOSED:
        logger.info("消息确认完成: message_id=%s, status=%s -> CLOSED", message.id, previous_status)
        await async_update_records(
            QQRobotMessage,
            {"id": message.id},
            {"status": QQRobotMessage.MessageStatus.CLOSED},
        )
        new_status = QQRobotMessage.MessageStatus.CLOSED
        status_changed = True
    elif not completed and previous_status == QQRobotMessage.MessageStatus.CLOSED:
        logger.info("消息确认未完成: message_id=%s, status=CLOSED -> SENT", message.id)
        await async_update_records(
            QQRobotMessage,
            {"id": message.id},
            {"status": QQRobotMessage.MessageStatus.SENT},
        )
        new_status = QQRobotMessage.MessageStatus.SENT
        status_changed = True

    if status_changed:
        message.status = new_status

    return completed, outstanding, status_changed, new_status


async def record_reaction(
    identifier: TrackedMessageIdentifier,
    reactor_uin: int,
    reaction_type: str,
    raw_event: Dict[str, Any],
) -> Optional[Tuple[bool, List[int], bool, str]]:
    message = await _resolve_message(identifier)
    if not message:
        logger.warning("Ack tracker: 未找到消息记录 identifier=%s", identifier)
        return None

    logger.info(
        "记录表情反应: message_id=%s, reactor_uin=%s, reaction_type=%s",
        message.id, reactor_uin, reaction_type
    )

    existing = await async_get_one(
        QQMessageReaction,
        message_id=message.id,
        reactor_uin=reactor_uin,
    )

    if existing:
        logger.info("更新已有表情反应记录: reaction_id=%s, reaction_type=%s -> %s", existing.id, existing.reaction_type, reaction_type)
        # 使用 async_update_records 确保更新被正确提交到数据库
        affected = await async_update_records(
            QQMessageReaction,
            {"id": existing.id},
            {
                "reaction_type": reaction_type,
                "raw_event": raw_event,
            },
        )
        if affected == 0:
            logger.warning("更新表情反应记录失败: reaction_id=%s, affected=%s", existing.id, affected)
    else:
        logger.info("创建新表情反应记录: message_id=%s, reactor_uin=%s, reaction_type=%s", message.id, reactor_uin, reaction_type)
        await async_create_record(
            QQMessageReaction,
            message_id=message.id,
            reactor_uin=reactor_uin,
            reaction_type=reaction_type,
            raw_event=raw_event,
        )

    return await _recompute_summary(message)


async def remove_reaction(
    identifier: TrackedMessageIdentifier,
    reactor_uin: int,
) -> Optional[Tuple[bool, List[int], bool, str]]:
    message = await _resolve_message(identifier)
    if not message:
        logger.debug("Ack tracker: message not found for removal %s", identifier)
        return None

    deleted = await async_delete_records(
        QQMessageReaction,
        message_id=message.id,
        reactor_uin=reactor_uin,
    )
    if not deleted:
        return await _recompute_summary(message)

    return await _recompute_summary(message)


async def mark_cancelled(message_id: str) -> bool:
    affected = await async_update_records(
        QQRobotMessage,
        {"id": message_id},
        {"status": QQRobotMessage.MessageStatus.CANCELLED},
    )
    return affected > 0



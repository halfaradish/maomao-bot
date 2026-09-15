"""
消息日志查询 API — 为 WebUI 消息日志页提供分页/过滤查询。

数据来源：messages_event_logs 表（logging_info 插件写入），
已有 idx_user_id / idx_group_id / idx_time / idx_type_group 索引。
"""
from fastapi import APIRouter, Depends, Query, Request

from src.api.deps import TokenPayload, verify_token
from src.api.permissions import _build_page_data, _paginate_query
from src.common.database import async_session_factory
from src.common.models.botdb_models import MessageEventLog
from src.config.response import success
from sqlalchemy import select

router = APIRouter(prefix="/logs", tags=["消息日志"])


@router.get("/messages", summary="分页查询消息日志")
async def list_messages(
    page: int = Query(1, ge=1, description="页码"),
    size: int = Query(20, ge=1, le=100, description="每页数量"),
    group_id: int = Query(None, description="按群号过滤"),
    user_id: int = Query(None, description="按QQ号过滤"),
    keyword: str = Query(None, description="消息内容关键词（模糊匹配）"),
    message_type: str = Query(None, description="消息类型，如 group/private"),
    start_time: int = Query(None, description="起始时间戳（秒）"),
    end_time: int = Query(None, description="结束时间戳（秒）"),
    auth: TokenPayload = Depends(verify_token),
    request: Request = None,
):
    """按条件分页查询消息日志，按发送时间倒序。"""
    stmt = select(MessageEventLog)
    if group_id is not None:
        stmt = stmt.where(MessageEventLog.group_id == group_id)
    if user_id is not None:
        stmt = stmt.where(MessageEventLog.user_id == user_id)
    if keyword:
        stmt = stmt.where(MessageEventLog.raw_message.icontains(keyword))
    if message_type:
        stmt = stmt.where(MessageEventLog.message_type == message_type)
    if start_time is not None:
        stmt = stmt.where(MessageEventLog.time >= start_time)
    if end_time is not None:
        stmt = stmt.where(MessageEventLog.time <= end_time)
    stmt = stmt.order_by(MessageEventLog.time.desc(), MessageEventLog.id.desc())

    async with async_session_factory() as session:
        rows, total = await _paginate_query(session, stmt, page, size)

    items = [
        {
            "id": r.id,
            "message_id": r.message_id,
            "time": r.time,
            "group_id": r.group_id,
            "user_id": r.user_id,
            "sender_nickname": r.sender_nickname,
            "sender_card": r.sender_card,
            "sender_role": r.sender_role,
            "message_type": r.message_type,
            "sub_type": r.sub_type,
            "to_me": r.to_me,
            "raw_message": r.raw_message,
        }
        for r in rows
    ]
    return success(data=_build_page_data(items, total, page, size), request=request)

# dao/message_dao.py
from nonebot import logger
from typing import List, Dict
import json
from datetime import datetime
import pytz
from django.db import IntegrityError
from django.utils import timezone
from ...common.django_crud import async_create_record, async_get_many, init_django_if_needed

init_django_if_needed()
from  botdb.models import MessageEventLog

# 北京时区
BEIJING_TZ = pytz.timezone("Asia/Shanghai")


def _convert_to_beijing_time(dt) -> datetime:
    """
    将 datetime 对象转换为北京时间
    :param dt: datetime 对象（可能是 timezone-aware 或 naive）
    :return: 北京时间的 datetime 对象（timezone-aware）
    """
    if dt is None:
        return None
    if timezone.is_aware(dt):
        # 如果是 timezone-aware，转换为北京时间
        return dt.astimezone(BEIJING_TZ)
    else:
        # 如果是 naive datetime，当 USE_TZ = False 时，它已经是北京时区的时间
        # 直接将其标记为北京时区
        return BEIJING_TZ.localize(dt)


def _format_datetime(dt: datetime, include_microseconds: bool = False) -> str:
    """
    格式化 datetime 为字符串
    :param dt: datetime 对象
    :param include_microseconds: 是否包含微秒
    :return: 格式化的时间字符串
    """
    if dt is None:
        return None
    if include_microseconds:
        return dt.strftime("%Y-%m-%d %H:%M:%S.%f")
    else:
        return dt.strftime("%Y-%m-%d %H:%M:%S")


class MessageDAO:
    """
    消息数据访问对象（DAO），用于操作 messages_event_logs 表
    """

    @staticmethod
    def create_table():
        """由 Django 迁移管理，无需手动建表"""
        logger.info("由 Django 迁移管理 `messages_event_logs` 表结构")

    @staticmethod
    async def save_message(event_data: Dict) -> bool:
        """
        保存一条消息事件
        :param event_data: 从 MessageEvent.dict() 得到的数据
        :return: 是否成功
        """
        try:
            params = MessageDAO._extract_params(event_data)
            # 存在唯一约束 message_id，重复则忽略更新 updated_at 由 ORM 维护
            await async_create_record(MessageEventLog, **params)
            return True
        # except IntegrityError:
        #     # 已存在同 message_id 记录，忽略
        #     return True
        except Exception as e:
            logger.error(f"保存消息失败 (message_id={event_data.get('message_id')}): {e}")
            return False

    @staticmethod
    def _extract_params(event_data: Dict) -> Dict:
        """从 event 数据中提取插入参数"""
        sender = event_data.get("sender", {}) or {}
        anonymous = event_data.get("anonymous", {}) or {}

        return {
            "message_id": event_data["message_id"],
            "self_id": event_data["self_id"],
            "user_id": event_data["user_id"],
            "message_type": event_data["message_type"],
            "group_id": event_data.get("group_id"),
            "sub_type": event_data["sub_type"],
            "post_type": event_data["post_type"],
            "time": event_data["time"],
            "raw_message": event_data["raw_message"],
            "message_json": event_data.get("message"),
            "to_me": event_data["to_me"],
            "reply_json": event_data.get("reply"),

            # sender 字段
            "sender_nickname": sender.get("nickname", ""),
            "sender_card": sender.get("card"),
            "sender_sex": sender.get("sex", "unknown"),
            "sender_age": sender.get("age"),
            "sender_role": sender.get("role", "member"),

            # anonymous 字段
            "anonymous_flag": anonymous.get("flag"),
            "anonymous_name": anonymous.get("name"),
            "anonymous_id": anonymous.get("id"),
        }

    @staticmethod
    async def get_recent_messages(limit: int = 100) -> List[Dict]:
        """获取最近 N 条消息"""
        try:
            rows = await async_get_many(
                MessageEventLog,
                filters=None,
                order_by=["-time"],
                limit=limit,
            )
            result = []
            for r in rows:
                # 转换 created_at 和 updated_at 为北京时间
                created_at_beijing = _convert_to_beijing_time(r.created_at)
                updated_at_beijing = _convert_to_beijing_time(r.updated_at)
                
                # 将 time 字段（Unix 时间戳，UTC）转换为北京时间字符串
                time_str = None
                if r.time:
                    # OneBot 的 time 字段是 UTC 时间戳，先转换为 UTC datetime，再转换为北京时间
                    dt_utc = datetime.fromtimestamp(r.time, tz=pytz.UTC)
                    dt_beijing = dt_utc.astimezone(BEIJING_TZ)
                    time_str = _format_datetime(dt_beijing, include_microseconds=False)
                
                result.append({
                    "message_id": r.message_id,
                    "user_id": r.user_id,
                    "group_id": r.group_id,
                    "raw_message": r.raw_message,
                    "time": r.time,
                    "time_str": time_str,  # 添加可读的时间字符串（北京时间）
                    "created_at": _format_datetime(created_at_beijing, include_microseconds=False),
                    "updated_at": _format_datetime(updated_at_beijing, include_microseconds=False),
                    "sender_nickname": r.sender_nickname,
                    "sender_card": r.sender_card,
                })
            return result
        except Exception as e:
            logger.error(f"查询最近消息失败: {e}")
            return []

    @staticmethod
    async def search_messages_by_keyword(keyword: str, limit: int = 50) -> List[Dict]:
        """根据关键词模糊搜索消息"""
        try:
            from django.db.models import Q
            from asgiref.sync import sync_to_async
            
            def _search_sync():
                return list(
                    MessageEventLog.objects.filter(
                        Q(raw_message__icontains=keyword)
                    ).order_by("-time")[:limit]
                )
            
            rows = await sync_to_async(_search_sync)()
            result = []
            for r in rows:
                # 转换 created_at 和 updated_at 为北京时间
                created_at_beijing = _convert_to_beijing_time(r.created_at)
                updated_at_beijing = _convert_to_beijing_time(r.updated_at)
                
                # 将 time 字段（Unix 时间戳，UTC）转换为北京时间字符串
                time_str = None
                if r.time:
                    # OneBot 的 time 字段是 UTC 时间戳，先转换为 UTC datetime，再转换为北京时间
                    dt_utc = datetime.fromtimestamp(r.time, tz=pytz.UTC)
                    dt_beijing = dt_utc.astimezone(BEIJING_TZ)
                    time_str = _format_datetime(dt_beijing, include_microseconds=False)
                
                result.append({
                    "message_id": r.message_id,
                    "user_id": r.user_id,
                    "group_id": r.group_id,
                    "raw_message": r.raw_message,
                    "time": r.time,
                    "time_str": time_str,  # 添加可读的时间字符串（北京时间）
                    "created_at": _format_datetime(created_at_beijing, include_microseconds=False),
                    "updated_at": _format_datetime(updated_at_beijing, include_microseconds=False),
                    "sender_nickname": r.sender_nickname,
                })
            return result
        except Exception as e:
            logger.error(f"搜索消息失败 (keyword={keyword}): {e}")
            return []
        

message_dao = MessageDAO()
message_dao.create_table()
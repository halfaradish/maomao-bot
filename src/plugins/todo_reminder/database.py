"""
Todo提醒插件数据库操作类
"""

from typing import Dict, List, Optional, Any, Tuple
from datetime import datetime, timedelta
from nonebot import logger
from sqlalchemy import and_, delete as sa_delete, update as sa_update, select

from ...common.crud import (
    async_create_record,
    async_get_one,
    async_get_many,
    async_update_records,
)
from ...common.database import async_session_factory
from ...common.models.botdb_models import TodoReminder, TodoReminderLog


class TodoDatabase:
    """Todo提醒数据库操作类"""
    
    def __init__(self):
        pass
    
    @staticmethod
    def _ensure_naive_local(dt: Optional[datetime]) -> Optional[datetime]:
        """
        将传入时间标准化为本地时区的 naive datetime。
        当 settings.USE_TZ=False 时，MySQL 不支持带 tzinfo 的 datetime。
        """
        if dt is None:
            return None
        if dt.tzinfo is not None and dt.tzinfo.utcoffset(dt) is not None:
            return dt.replace(tzinfo=None)
        return dt
    
    @staticmethod
    def _coerce_int_user(value: Any, fallback: int) -> int:
        """
        将用户标识转换为整数。若传入为昵称或无法解析为数字，则回退为 fallback。
        """
        if isinstance(value, int):
            return value
        if isinstance(value, str):
            value_str = value.strip()
            if value_str.isdigit():
                try:
                    return int(value_str)
                except Exception:
                    return fallback
        return fallback
    
    async def create_reminder(self, reminder_data: Dict[str, Any]) -> int:
        """创建提醒"""
        try:
            remind_time = self._ensure_naive_local(reminder_data['remind_time'])
            # 保障操作者与修改者为整数ID；若提供的是昵称则回退为 user_id
            user_id_int = self._coerce_int_user(reminder_data['user_id'], fallback=0)
            created_by_int = self._coerce_int_user(reminder_data.get('created_by', user_id_int), fallback=user_id_int)
            last_modified_by_int = self._coerce_int_user(reminder_data.get('last_modified_by', user_id_int), fallback=created_by_int)
            obj = await async_create_record(
                TodoReminder,
                group_id=reminder_data['group_id'],
                user_id=user_id_int,
                target_user_id=reminder_data.get('target_user_id'),
                content=reminder_data['content'],
                remind_time=remind_time,
                remind_type=reminder_data.get('remind_type', 'once'),
                status=reminder_data.get('status', 'pending'),
                created_by=created_by_int,
                last_modified_by=last_modified_by_int,
                advance_remind_minutes=reminder_data.get('advance_remind_minutes', 0),
                advance_reminded=reminder_data.get('advance_reminded', False)
            )
            return obj.id
        except Exception as e:
            logger.error(f"创建提醒失败: {e}")
            raise
    
    async def get_reminder(self, reminder_id: int) -> Optional[Dict[str, Any]]:
        """获取提醒详情"""
        try:
            obj = await async_get_one(TodoReminder, id=reminder_id)
            return None if not obj else self._to_dict(obj)
        except Exception as e:
            logger.error(f"获取提醒失败: {e}")
            return None
    
    async def get_user_reminders(self, user_id: int, group_id: int, 
                          status: str = 'pending') -> List[Dict[str, Any]]:
        """获取用户提醒列表"""
        try:
            rows = await async_get_many(
                TodoReminder,
                filters={'user_id': user_id, 'group_id': group_id, 'status': status},
                order_by=['remind_time']
            )
            return [self._to_dict(r) for r in rows]
        except Exception as e:
            logger.error(f"获取用户提醒列表失败: {e}")
            logger.error(f"错误类型: {type(e).__name__}")
            logger.error(f"参数: user_id={user_id}, group_id={group_id}, status={status}")
            import traceback
            logger.error(f"错误堆栈: {traceback.format_exc()}")
            return []
    
    async def get_group_reminders(self, group_id: int, status: str = 'pending') -> List[Dict[str, Any]]:
        """获取群组提醒列表"""
        try:
            rows = await async_get_many(
                TodoReminder,
                filters={'group_id': group_id, 'status': status},
                order_by=['remind_time']
            )
            return [self._to_dict(r) for r in rows]
        except Exception as e:
            logger.error(f"获取群组提醒列表失败: {e}")
            return []
    
    async def get_group_shared_reminders(self, group_id: int, status: str = 'pending') -> List[Dict[str, Any]]:
        """获取群组共享提醒列表（群内所有用户可见）"""
        try:
            rows = await async_get_many(
                TodoReminder,
                filters={'group_id': group_id, 'status': status},
                order_by=['remind_time']
            )
            return [self._to_dict(r) for r in rows]
        except Exception as e:
            logger.error(f"获取群组共享提醒列表失败: {e}")
            return []
    
    async def get_pending_reminders(self, limit: int = 100) -> List[Dict[str, Any]]:
        """获取待执行的提醒"""
        try:
            rows = await async_get_many(
                TodoReminder,
                filters={"status": "pending", "remind_time__lte": datetime.now()},
                order_by=["remind_time"],
                limit=limit,
            )
            return [self._to_dict(r) for r in rows]
        except Exception as e:
            logger.error(f"获取待执行提醒失败: {e}")
            return []
    
    async def update_reminder_status(self, reminder_id: int, status: str,
                              error_message: str = None) -> bool:
        """更新提醒状态"""
        try:
            if status == 'completed':
                # 原子递增 execution_count
                async with async_session_factory() as session:
                    stmt = (
                        sa_update(TodoReminder)
                        .where(TodoReminder.id == reminder_id)
                        .values(
                            status=status,
                            executed_at=datetime.now(),
                            execution_count=TodoReminder.execution_count + 1,
                        )
                    )
                    await session.execute(stmt)
                    if error_message:
                        stmt2 = (
                            sa_update(TodoReminder)
                            .where(TodoReminder.id == reminder_id)
                            .values(error_message=error_message)
                        )
                        await session.execute(stmt2)
                    await session.commit()
                return True
            updates: Dict[str, Any] = {'status': status}
            if status == 'failed' and error_message:
                updates['error_message'] = error_message
            affected = await async_update_records(TodoReminder, {'id': reminder_id}, updates)
            return affected > 0
        except Exception as e:
            logger.error(f"更新提醒状态失败: {e}")
            return False
    
    async def delete_reminder(self, reminder_id: int, user_id: int) -> bool:
        """删除提醒（个人）"""
        try:
            async with async_session_factory() as session:
                stmt = sa_delete(TodoReminder).where(
                    TodoReminder.id == reminder_id,
                    TodoReminder.user_id == user_id,
                )
                result = await session.execute(stmt)
                await session.commit()
                return result.rowcount > 0
        except Exception as e:
            logger.error(f"删除提醒失败: {e}")
            return False

    async def delete_group_shared_reminder(self, reminder_id: int, group_id: int) -> bool:
        """删除群组共享提醒（群内任何用户都可以删除）"""
        try:
            async with async_session_factory() as session:
                stmt = sa_delete(TodoReminder).where(
                    TodoReminder.id == reminder_id,
                    TodoReminder.group_id == group_id,
                )
                result = await session.execute(stmt)
                await session.commit()
                return result.rowcount > 0
        except Exception as e:
            logger.error(f"删除群组共享提醒失败: {e}")
            return False


    async def cleanup_old_reminders(self, days: int = 30) -> int:
        """清理旧的已完成提醒"""
        try:
            cutoff_date = datetime.now() - timedelta(days=days)
            async with async_session_factory() as session:
                stmt = sa_delete(TodoReminder).where(
                    and_(
                        TodoReminder.status.in_(['completed', 'cancelled']),
                        TodoReminder.executed_at < cutoff_date,
                    )
                )
                result = await session.execute(stmt)
                await session.commit()
                return result.rowcount
        except Exception as e:
            logger.error(f"清理旧提醒失败: {e}")
            return 0
    
    async def log_reminder_execution(self, reminder_id: int, status: str, 
                              error_message: str = None, execution_duration: int = None):
        """记录提醒执行日志"""
        try:
            await async_create_record(
                TodoReminderLog,
                reminder_id=reminder_id,
                status=status,
                error_message=error_message,
                execution_duration_ms=execution_duration
            )
        except Exception as e:
            logger.error(f"记录提醒执行日志失败: {e}")
    
    async def mark_advance_reminded(self, reminder_id: int) -> bool:
        """标记提前提醒已发送"""
        try:
            affected = await async_update_records(TodoReminder, {'id': reminder_id}, {'advance_reminded': True})
            return affected > 0
        except Exception as e:
            logger.error(f"标记提前提醒失败: {e}")
            return False
    
    async def get_advance_reminders(self, current_time: datetime) -> List[Dict[str, Any]]:
        """获取需要发送提前提醒的提醒列表"""
        try:
            current_time = self._ensure_naive_local(current_time)
            # 先从数据库获取待筛选的候选提醒
            rows = await async_get_many(
                TodoReminder,
                filters={
                    "status": "pending",
                    "advance_remind_minutes__gt": 0,
                    "advance_reminded": False,
                    "remind_time__gt": current_time,
                },
            )
            # 在 Python 侧做进一步的时间计算筛选
            result: List[Dict[str, Any]] = []
            for r in rows:
                advance_minutes = r.advance_remind_minutes or 0
                remind_time = r.remind_time
                advance_time = remind_time - timedelta(minutes=advance_minutes)
                if advance_time <= current_time:
                    result.append(self._to_dict(r))
            return result
        except Exception as e:
            logger.error(f"获取提前提醒列表失败: {e}")
            return []
    
    def _to_dict(self, r: TodoReminder) -> Dict[str, Any]:
        return {
            "id": r.id,
            "group_id": r.group_id,
            "user_id": r.user_id,
            "target_user_id": r.target_user_id,
            "content": r.content,
            "remind_time": r.remind_time,
            "remind_type": r.remind_type,
            "status": r.status,
            "created_by": r.created_by,
            "last_modified_by": r.last_modified_by,
            "advance_remind_minutes": r.advance_remind_minutes,
            "advance_reminded": r.advance_reminded,
            "execution_count": r.execution_count,
            "executed_at": r.executed_at,
            "error_message": r.error_message,
            "created_at": r.created_at,
            "updated_at": r.updated_at,
        }
    

"""
Todo提醒插件数据库操作类
"""

from typing import Dict, List, Optional, Any, Tuple
from datetime import datetime, timedelta
from nonebot import logger
from asgiref.sync import sync_to_async
from django.utils import timezone

from ...common.django_crud import (
    async_create_record,
    async_get_one,
    async_get_many,
    async_update_records,
    init_django_if_needed,
)

# 确保 Django 环境初始化后再导入 ORM 模型
init_django_if_needed()
from botdb.models import TodoReminder, TodoReminderLog


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
        if timezone.is_aware(dt):
            return timezone.make_naive(dt, timezone.get_current_timezone())
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
            def _get_pending_sync():
                return list(
                    TodoReminder.objects.filter(
                        status='pending',
                        remind_time__lte=datetime.now(),
                    ).order_by('remind_time')[:limit]
                )
            rows = await sync_to_async(_get_pending_sync)()
            return [self._to_dict(r) for r in rows]
        except Exception as e:
            logger.error(f"获取待执行提醒失败: {e}")
            return []
    
    async def update_reminder_status(self, reminder_id: int, status: str, 
                              error_message: str = None) -> bool:
        """更新提醒状态"""
        try:
            updates: Dict[str, Any] = {'status': status}
            if status == 'completed':
                updates['executed_at'] = datetime.now()
                from django.db.models import F
                
                def _update_completed_sync():
                    TodoReminder.objects.filter(id=reminder_id).update(**updates, execution_count=F('execution_count') + 1)
                    if error_message:
                        TodoReminder.objects.filter(id=reminder_id).update(error_message=error_message)
                
                await sync_to_async(_update_completed_sync)()
                return True
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
            def _delete_sync():
                deleted, _ = TodoReminder.objects.filter(id=reminder_id, user_id=user_id).delete()
                return deleted
            
            deleted = await sync_to_async(_delete_sync)()
            return deleted > 0
        except Exception as e:
            logger.error(f"删除提醒失败: {e}")
            return False
    
    async def delete_group_shared_reminder(self, reminder_id: int, group_id: int) -> bool:
        """删除群组共享提醒（群内任何用户都可以删除）"""
        try:
            def _delete_sync():
                deleted, _ = TodoReminder.objects.filter(id=reminder_id, group_id=group_id).delete()
                return deleted
            
            deleted = await sync_to_async(_delete_sync)()
            return deleted > 0
        except Exception as e:
            logger.error(f"删除群组共享提醒失败: {e}")
            return False
    
    
    async def cleanup_old_reminders(self, days: int = 30) -> int:
        """清理旧的已完成提醒"""
        try:
            cutoff_date = datetime.now() - timedelta(days=days)
            from django.db.models import Q
            
            def _cleanup_sync():
                deleted, _ = TodoReminder.objects.filter(
                    Q(status__in=['completed', 'cancelled']) & Q(executed_at__lt=cutoff_date)
                ).delete()
                return deleted
            
            deleted = await sync_to_async(_cleanup_sync)()
            return deleted
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
            def _to_dict_inline(r: TodoReminder) -> Dict[str, Any]:
                """内联的 _to_dict 方法"""
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
            
            def _get_advance_sync():
                reminders = list(
                    TodoReminder.objects.filter(
                        status='pending',
                        advance_remind_minutes__gt=0,
                        advance_reminded=False,
                        remind_time__gt=current_time
                    )
                )
                result: List[Dict[str, Any]] = []
                for r in reminders:
                    advance_minutes = r.advance_remind_minutes or 0
                    remind_time = r.remind_time
                    advance_time = remind_time - timedelta(minutes=advance_minutes)
                    if advance_time <= current_time:
                        result.append(_to_dict_inline(r))
                return result
            
            return await sync_to_async(_get_advance_sync)()
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
    

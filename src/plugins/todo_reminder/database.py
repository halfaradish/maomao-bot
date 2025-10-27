"""
Todo提醒插件数据库操作类
"""

from typing import Dict, List, Optional, Any, Tuple
from datetime import datetime, timedelta
import json
from mysql.connector import Error
from nonebot import logger

from ...common.diting_db_pool import get_diting_db_connection


class TodoDatabase:
    """Todo提醒数据库操作类"""
    
    def __init__(self):
        self.connection_func = get_diting_db_connection
    
    def create_reminder(self, reminder_data: Dict[str, Any]) -> int:
        """创建提醒"""
        try:
            with self.connection_func() as conn:
                cursor = conn.execute("""
                    INSERT INTO todo_reminders 
                    (group_id, user_id, target_user_id, content, remind_time, 
                     remind_type, status, created_by, last_modified_by, 
                     advance_remind_minutes, advance_reminded)
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                """, (
                    reminder_data['group_id'],
                    reminder_data['user_id'],
                    reminder_data.get('target_user_id'),
                    reminder_data['content'],
                    reminder_data['remind_time'],
                    reminder_data.get('remind_type', 'once'),
                    reminder_data.get('status', 'pending'),
                    reminder_data['created_by'],
                    reminder_data['last_modified_by'],
                    reminder_data.get('advance_remind_minutes', 0),
                    reminder_data.get('advance_reminded', False)
                ))
                return cursor.lastrowid
        except Exception as e:
            logger.error(f"创建提醒失败: {e}")
            raise
    
    def get_reminder(self, reminder_id: int) -> Optional[Dict[str, Any]]:
        """获取提醒详情"""
        try:
            with self.connection_func() as conn:
                cursor = conn.execute("""
                    SELECT * FROM todo_reminders WHERE id = %s
                """, (reminder_id,))
                return cursor.fetchone()
        except Exception as e:
            logger.error(f"获取提醒失败: {e}")
            return None
    
    def get_user_reminders(self, user_id: int, group_id: int, 
                          status: str = 'pending') -> List[Dict[str, Any]]:
        """获取用户提醒列表"""
        try:
            with self.connection_func() as conn:
                cursor = conn.execute("""
                    SELECT * FROM todo_reminders 
                    WHERE user_id = %s AND group_id = %s AND status = %s
                    ORDER BY remind_time ASC
                """, (user_id, group_id, status))
                return cursor.fetchall()
        except Exception as e:
            logger.error(f"获取用户提醒列表失败: {e}")
            logger.error(f"错误类型: {type(e).__name__}")
            logger.error(f"参数: user_id={user_id}, group_id={group_id}, status={status}")
            import traceback
            logger.error(f"错误堆栈: {traceback.format_exc()}")
            return []
    
    def get_group_reminders(self, group_id: int, status: str = 'pending') -> List[Dict[str, Any]]:
        """获取群组提醒列表"""
        try:
            with self.connection_func() as conn:
                cursor = conn.execute("""
                    SELECT * FROM todo_reminders 
                    WHERE group_id = %s AND status = %s
                    ORDER BY remind_time ASC
                """, (group_id, status))
                return cursor.fetchall()
        except Exception as e:
            logger.error(f"获取群组提醒列表失败: {e}")
            return []
    
    def get_group_shared_reminders(self, group_id: int, status: str = 'pending') -> List[Dict[str, Any]]:
        """获取群组共享提醒列表（群内所有用户可见）"""
        try:
            with self.connection_func() as conn:
                cursor = conn.execute("""
                    SELECT * FROM todo_reminders 
                    WHERE group_id = %s AND status = %s
                    ORDER BY remind_time ASC
                """, (group_id, status))
                return cursor.fetchall()
        except Exception as e:
            logger.error(f"获取群组共享提醒列表失败: {e}")
            return []
    
    def get_pending_reminders(self, limit: int = 100) -> List[Dict[str, Any]]:
        """获取待执行的提醒"""
        try:
            with self.connection_func() as conn:
                cursor = conn.execute("""
                    SELECT * FROM todo_reminders 
                    WHERE status = 'pending' AND remind_time <= %s
                    ORDER BY remind_time ASC
                    LIMIT %s
                """, (datetime.now(), limit))
                return cursor.fetchall()
        except Exception as e:
            logger.error(f"获取待执行提醒失败: {e}")
            return []
    
    def update_reminder_status(self, reminder_id: int, status: str, 
                              error_message: str = None) -> bool:
        """更新提醒状态"""
        try:
            with self.connection_func() as conn:
                update_data = {
                    'status': status,
                    'updated_at': datetime.now()
                }
                
                if status == 'completed':
                    update_data['executed_at'] = datetime.now()
                    update_data['execution_count'] = 'execution_count + 1'
                elif status == 'failed' and error_message:
                    update_data['error_message'] = error_message
                
                if 'execution_count' in update_data:
                    conn.execute("""
                        UPDATE todo_reminders 
                        SET status = %s, updated_at = %s, executed_at = %s, 
                            execution_count = execution_count + 1, error_message = %s
                        WHERE id = %s
                    """, (status, update_data['updated_at'], update_data['executed_at'], 
                          error_message, reminder_id))
                else:
                    conn.execute("""
                        UPDATE todo_reminders 
                        SET status = %s, updated_at = %s, error_message = %s
                        WHERE id = %s
                    """, (status, update_data['updated_at'], error_message, reminder_id))
                
                return True
        except Exception as e:
            logger.error(f"更新提醒状态失败: {e}")
            return False
    
    def delete_reminder(self, reminder_id: int, user_id: int) -> bool:
        """删除提醒（个人）"""
        try:
            with self.connection_func() as conn:
                cursor = conn.execute("""
                    DELETE FROM todo_reminders 
                    WHERE id = %s AND user_id = %s
                """, (reminder_id, user_id))
                return cursor.rowcount > 0
        except Exception as e:
            logger.error(f"删除提醒失败: {e}")
            return False
    
    def delete_group_shared_reminder(self, reminder_id: int, group_id: int) -> bool:
        """删除群组共享提醒（群内任何用户都可以删除）"""
        try:
            with self.connection_func() as conn:
                cursor = conn.execute("""
                    DELETE FROM todo_reminders 
                    WHERE id = %s AND group_id = %s
                """, (reminder_id, group_id))
                return cursor.rowcount > 0
        except Exception as e:
            logger.error(f"删除群组共享提醒失败: {e}")
            return False
    
    
    def cleanup_old_reminders(self, days: int = 30) -> int:
        """清理旧的已完成提醒"""
        try:
            with self.connection_func() as conn:
                cutoff_date = datetime.now() - timedelta(days=days)
                cursor = conn.execute("""
                    DELETE FROM todo_reminders 
                    WHERE status IN ('completed', 'cancelled') 
                    AND executed_at < %s
                """, (cutoff_date,))
                return cursor.rowcount
        except Exception as e:
            logger.error(f"清理旧提醒失败: {e}")
            return 0
    
    def log_reminder_execution(self, reminder_id: int, status: str, 
                              error_message: str = None, execution_duration: int = None):
        """记录提醒执行日志"""
        try:
            with self.connection_func() as conn:
                conn.execute("""
                    INSERT INTO todo_reminder_logs 
                    (reminder_id, status, error_message, execution_duration_ms)
                    VALUES (%s, %s, %s, %s)
                """, (reminder_id, status, error_message, execution_duration))
        except Exception as e:
            logger.error(f"记录提醒执行日志失败: {e}")
    
    def mark_advance_reminded(self, reminder_id: int) -> bool:
        """标记提前提醒已发送"""
        try:
            with self.connection_func() as conn:
                cursor = conn.execute("""
                    UPDATE todo_reminders 
                    SET advance_reminded = TRUE 
                    WHERE id = %s
                """, (reminder_id,))
                return cursor.rowcount > 0
        except Exception as e:
            logger.error(f"标记提前提醒失败: {e}")
            return False
    
    def get_advance_reminders(self, current_time: datetime) -> List[Dict[str, Any]]:
        """获取需要发送提前提醒的提醒列表"""
        try:
            with self.connection_func() as conn:
                cursor = conn.execute("""
                    SELECT * FROM todo_reminders 
                    WHERE status = 'pending' 
                    AND advance_remind_minutes > 0 
                    AND advance_reminded = FALSE
                    AND DATE_SUB(remind_time, INTERVAL advance_remind_minutes MINUTE) <= %s
                    AND remind_time > %s
                """, (current_time, current_time))
                return cursor.fetchall()
        except Exception as e:
            logger.error(f"获取提前提醒列表失败: {e}")
            return []
    

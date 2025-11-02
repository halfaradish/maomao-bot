"""
Todo提醒插件调度器
负责定时检查和执行提醒
"""

import asyncio
from datetime import datetime, timedelta
from typing import Dict, Any, List, Optional

from nonebot import logger, get_bot
from nonebot.adapters.onebot.v11 import Bot, MessageSegment

from .database import TodoDatabase
from .time_parser import TimeParser


class ReminderScheduler:
    """提醒调度器类"""
    
    def __init__(self, database: TodoDatabase, time_parser: TimeParser):
        self.database = database
        self.time_parser = time_parser
        self.running = False
        self.task = None
        self.check_interval = 60  # 检查间隔(秒)
    
    async def start(self):
        """启动调度器"""
        if self.running:
            logger.warning("提醒调度器已在运行")
            return
        
        self.running = True
        self.task = asyncio.create_task(self._scheduler_loop())
        logger.info("提醒调度器已启动")
    
    async def stop(self):
        """停止调度器"""
        if not self.running:
            return
        
        self.running = False
        if self.task:
            self.task.cancel()
            try:
                await self.task
            except asyncio.CancelledError:
                pass
        
        logger.info("提醒调度器已停止")
    
    async def _scheduler_loop(self):
        """调度器主循环"""
        while self.running:
            try:
                await self._check_and_execute_reminders()
                await asyncio.sleep(self.check_interval)
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"提醒调度器错误: {e}")
                await asyncio.sleep(self.check_interval)
    
    async def _check_and_execute_reminders(self):
        """检查并执行到期的提醒"""
        try:
            current_time = datetime.now()
            
            # 1. 检查需要发送提前提醒的提醒
            await self._check_and_send_advance_reminders(current_time)
            
            # 2. 获取待执行的提醒
            pending_reminders = self.database.get_pending_reminders(limit=100)
            if not pending_reminders:
                return
            
            logger.info(f"检查到 {len(pending_reminders)} 个待执行提醒")
            
            for reminder in pending_reminders:
                try:
                    await self._execute_reminder(reminder)
                except Exception as e:
                    logger.error(f"执行提醒失败 {reminder['id']}: {e}")
                    # 尝试重试失败的提醒
                    await self._handle_failed_reminder(reminder, str(e))
                    
        except Exception as e:
            logger.error(f"检查提醒时发生错误: {e}")
    
    async def _check_and_send_advance_reminders(self, current_time: datetime):
        """检查并发送提前提醒"""
        try:
            # 获取需要发送提前提醒的提醒列表
            advance_reminders = self.database.get_advance_reminders(current_time)
            if not advance_reminders:
                return
            
            logger.info(f"检查到 {len(advance_reminders)} 个需要发送提前提醒的提醒")
            
            # 获取机器人实例
            bot = get_bot()
            if not bot:
                logger.error("无法获取机器人实例，跳过提前提醒")
                return
            
            for reminder in advance_reminders:
                try:
                    await self._send_advance_reminder(bot, reminder)
                    # 标记提前提醒已发送
                    self.database.mark_advance_reminded(reminder['id'])
                    logger.info(f"提前提醒发送成功: {reminder['id']}")
                except Exception as e:
                    logger.error(f"发送提前提醒失败 {reminder['id']}: {e}")
                    
        except Exception as e:
            logger.error(f"检查提前提醒时发生错误: {e}")
    
    async def _send_advance_reminder(self, bot: Bot, reminder: Dict[str, Any]):
        """发送提前提醒"""
        try:
            # 构建提前提醒消息
            message = self._build_advance_reminder_message(reminder)
            
            # 根据提醒类型发送消息
            if reminder['target_user_id'] == -1:
                # @全体成员提前提醒
                await self._send_group_at_all_reminder(bot, reminder, message)
            elif reminder['target_user_id']:
                # 指定用户提前提醒
                await self._send_group_mention_reminder(bot, reminder, message)
            else:
                # 群组提前提醒
                await self._send_group_reminder(bot, reminder, message)
                
        except Exception as e:
            logger.error(f"发送提前提醒失败: {e}")
            raise
    
    def _build_advance_reminder_message(self, reminder: Dict[str, Any]) -> str:
        """构建提前提醒消息"""
        remind_time_str = self.time_parser.format_remind_time(reminder['remind_time'])
        advance_minutes = reminder.get('advance_remind_minutes', 0)
        
        # 格式化提前时间显示
        if advance_minutes >= 60:
            hours = advance_minutes // 60
            minutes = advance_minutes % 60
            if minutes > 0:
                advance_display = f"{hours}小时{minutes}分钟"
            else:
                advance_display = f"{hours}小时"
        else:
            advance_display = f"{advance_minutes}分钟"
        
        if reminder['target_user_id'] == -1:
            # @全体成员提前提醒格式
            message = f"群组提前提醒\n"
            message += f"还有 {advance_display} 就到时间了！\n"
            message += f"提醒时间：{remind_time_str}\n"
            message += f"内容：{reminder['content']}\n"
            message += f"创建者：{reminder['created_by']}\n"
            message += f"提醒ID：{reminder['id']}"
        elif reminder['target_user_id']:
            # @用户提前提醒格式
            message = f"提前提醒\n"
            message += f"还有 {advance_display} 就到时间了！\n"
            message += f"提醒时间：{remind_time_str}\n"
            message += f"内容：{reminder['content']}\n"
            message += f"创建者：{reminder['created_by']}\n"
            message += f"提醒ID：{reminder['id']}"
        else:
            # 普通提前提醒格式
            message = f"提前提醒\n"
            message += f"还有 {advance_display} 就到时间了！\n"
            message += f"提醒时间：{remind_time_str}\n"
            message += f"内容：{reminder['content']}\n"
            message += f"创建者：{reminder['created_by']}\n"
            message += f"提醒ID：{reminder['id']}"
        
        return message
    
    async def _handle_failed_reminder(self, reminder: Dict[str, Any], error_message: str):
        """处理失败的提醒，决定是否重试"""
        try:
            # 获取当前执行次数
            execution_count = reminder.get('execution_count', 0) or 0
            
            # 检查配置（从 Config 类获取，这里使用默认值）
            max_retry_attempts = 3  # 可以从 config 获取
            retry_failed_reminders = True  # 可以从 config 获取
            
            if not retry_failed_reminders:
                # 如果配置不允许重试，直接标记为失败
                self.database.update_reminder_status(
                    reminder['id'], 'failed', error_message
                )
                self.database.log_reminder_execution(
                    reminder['id'], 'failed', error_message
                )
                return
            
            if execution_count < max_retry_attempts:
                # 还可以重试，重新设置为 pending 状态，等待下次执行
                # 注意：这里不更新 execution_count，让下次执行时再更新
                logger.info(f"提醒 {reminder['id']} 执行失败，将重试 (第 {execution_count + 1}/{max_retry_attempts} 次)")
                # 保持 pending 状态，等待下次执行
                self.database.log_reminder_execution(
                    reminder['id'], 'failed', error_message, execution_duration=None
                )
            else:
                # 超过最大重试次数，标记为失败
                logger.error(f"提醒 {reminder['id']} 超过最大重试次数，标记为失败")
                self.database.update_reminder_status(
                    reminder['id'], 'failed', error_message
                )
                self.database.log_reminder_execution(
                    reminder['id'], 'failed', error_message
                )
        except Exception as e:
            logger.error(f"处理失败提醒时发生错误: {e}")
    
    async def _execute_reminder(self, reminder: Dict[str, Any]):
        """执行单个提醒"""
        start_time = datetime.now()
        
        try:
            # 获取机器人实例
            bot = get_bot()
            if not bot:
                logger.error("无法获取机器人实例")
                return
            
            # 根据提醒类型发送消息
            if reminder['target_user_id'] == -1:
                # @全体成员提醒
                message = self._build_reminder_message(reminder, is_at_all=True)
                await self._send_group_at_all_reminder(bot, reminder, message)
            elif reminder['target_user_id']:
                # 指定用户提醒 - 发送到群组并@用户
                message = self._build_reminder_message(reminder, is_user_mention=True)
                await self._send_group_mention_reminder(bot, reminder, message)
            else:
                # 群组提醒 - 发送到群组
                message = self._build_reminder_message(reminder, is_user_mention=False)
                await self._send_group_reminder(bot, reminder, message)
            
            # 更新提醒状态为已完成
            self.database.update_reminder_status(reminder['id'], 'completed')
            
            # 记录执行日志
            execution_duration = int((datetime.now() - start_time).total_seconds() * 1000)
            self.database.log_reminder_execution(
                reminder['id'], 'success', execution_duration=execution_duration
            )
            
            logger.info(f"提醒执行成功: {reminder['id']}")
            
            # 如果是重复提醒，创建下一个提醒
            if reminder['remind_type'] in ['daily', 'weekly', 'monthly', 'workday']:
                await self._create_next_recurring_reminder(reminder)
                
        except Exception as e:
            logger.error(f"执行提醒失败: {e}")
            raise
    
    def _build_reminder_message(self, reminder: Dict[str, Any], is_user_mention: bool = False, is_at_all: bool = False) -> str:
        """构建提醒消息"""
        remind_time_str = self.time_parser.format_remind_time(reminder['remind_time'])
        
        if is_at_all:
            # @全体成员提醒格式
            message = f"群组提醒通知\n"
            message += f"时间：{remind_time_str}\n"
            message += f"内容：{reminder['content']}\n"
            message += f"创建者：{reminder['created_by']}\n"
            message += f"提醒ID：{reminder['id']}"
        elif is_user_mention:
            # @用户提醒格式
            message = f"提醒通知\n"
            message += f"时间：{remind_time_str}\n"
            message += f"内容：{reminder['content']}\n"
            message += f"创建者：{reminder['created_by']}\n"
            message += f"提醒ID：{reminder['id']}"
        else:
            # 普通提醒格式
            message = f"提醒通知\n"
            message += f"时间：{remind_time_str}\n"
            message += f"内容：{reminder['content']}\n"
            message += f"创建者：{reminder['created_by']}\n"
            message += f"提醒ID：{reminder['id']}"
        
        return message
    
    async def _send_group_reminder(self, bot: Bot, reminder: Dict[str, Any], message: str):
        """发送群组提醒"""
        try:
            await bot.send_group_msg(
                group_id=reminder['group_id'],
                message=message
            )
        except Exception as e:
            logger.error(f"发送群组提醒失败: {e}")
            raise
    
    async def _send_group_mention_reminder(self, bot: Bot, reminder: Dict[str, Any], message: str):
        """发送群组@用户提醒"""
        try:
            # 构建@用户的消息，在@后添加换行
            mention_message = MessageSegment.at(reminder['target_user_id']) + "\n" + message
            await bot.send_group_msg(
                group_id=reminder['group_id'],
                message=mention_message
            )
        except Exception as e:
            logger.error(f"发送群组@用户提醒失败: {e}")
            raise
    
    async def _send_group_at_all_reminder(self, bot: Bot, reminder: Dict[str, Any], message: str):
        """发送群组@全体成员提醒"""
        try:
            # 构建@全体成员的消息
            at_all_message = MessageSegment.at("all") + "\n" + message
            await bot.send_group_msg(
                group_id=reminder['group_id'],
                message=at_all_message
            )
        except Exception as e:
            logger.error(f"发送群组@全体成员提醒失败: {e}")
            raise
    
    async def _create_next_recurring_reminder(self, original_reminder: Dict[str, Any]):
        """创建下一个重复提醒"""
        try:
            next_remind_time = self._calculate_next_recurring_time(original_reminder)
            if not next_remind_time:
                return
            
            # 创建新的提醒数据
            new_reminder_data = {
                'group_id': original_reminder['group_id'],
                'user_id': original_reminder['user_id'],
                'target_user_id': original_reminder['target_user_id'],
                'content': original_reminder['content'],
                'remind_time': next_remind_time,
                'remind_type': original_reminder['remind_type'],
                'status': 'pending',
                'created_by': original_reminder['created_by'],
                'last_modified_by': original_reminder['last_modified_by']
            }
            
            # 保存新提醒
            reminder_id = self.database.create_reminder(new_reminder_data)
            logger.info(f"创建下一个重复提醒: {reminder_id}")
            
        except Exception as e:
            logger.error(f"创建下一个重复提醒失败: {e}")
    
    def _calculate_next_recurring_time(self, reminder: Dict[str, Any]) -> Optional[datetime]:
        """计算下一个重复提醒时间"""
        current_time = reminder['remind_time']
        remind_type = reminder['remind_type']
        
        if remind_type == 'daily':
            return current_time + timedelta(days=1)
        elif remind_type == 'weekly':
            return current_time + timedelta(weeks=1)
        elif remind_type == 'monthly':
            # 准确的月份计算，考虑月份天数差异
            try:
                from dateutil.relativedelta import relativedelta
                return current_time + relativedelta(months=1)
            except ImportError:
                # 如果 dateutil 不可用，使用简化版本
                # 添加一个月，考虑月末情况
                if current_time.month == 12:
                    next_year = current_time.year + 1
                    next_month = 1
                else:
                    next_year = current_time.year
                    next_month = current_time.month + 1
                
                # 处理日期超出月份天数的情况（如 1月31日 -> 2月28/29日）
                from calendar import monthrange
                last_day = monthrange(next_year, next_month)[1]
                next_day = min(current_time.day, last_day)
                
                return current_time.replace(year=next_year, month=next_month, day=next_day)
        elif remind_type == 'workday':
            return self._get_next_workday_time(current_time)
        
        return None
    
    def _get_next_workday_time(self, current_time: datetime) -> datetime:
        """获取下一个工作日的相同时间"""
        next_time = current_time + timedelta(days=1)
        # 跳过周末
        while next_time.weekday() >= 5:  # 周六是5，周日是6
            next_time += timedelta(days=1)
        return next_time
    
    async def execute_reminder_now(self, reminder_id: int) -> bool:
        """立即执行指定提醒"""
        try:
            reminder = self.database.get_reminder(reminder_id)
            if not reminder:
                logger.error(f"提醒不存在: {reminder_id}")
                return False
            
            if reminder['status'] != 'pending':
                logger.warning(f"提醒状态不是pending: {reminder_id}")
                return False
            
            await self._execute_reminder(reminder)
            return True
            
        except Exception as e:
            logger.error(f"立即执行提醒失败: {e}")
            return False
    
    async def cleanup_old_reminders(self, days: int = 30) -> int:
        """清理旧的已完成提醒"""
        try:
            cleaned_count = self.database.cleanup_old_reminders(days)
            logger.info(f"清理了 {cleaned_count} 个旧提醒")
            return cleaned_count
        except Exception as e:
            logger.error(f"清理旧提醒失败: {e}")
            return 0
    
    def get_scheduler_status(self) -> Dict[str, Any]:
        """获取调度器状态"""
        return {
            "running": self.running,
            "check_interval": self.check_interval,
            "task_running": self.task is not None and not self.task.done() if self.task else False
        }

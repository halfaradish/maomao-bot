"""
Todo提醒插件调度器
负责定时检查和执行提醒

轮询由 APScheduler 的 interval job 驱动（见 ``register_job``），不再自建
``while + asyncio.sleep`` 循环：起停交给 ``nonebot_plugin_apscheduler``，
本模块只提供「一轮检查」的入口 ``tick()``。
"""

from datetime import datetime, timedelta
from typing import Dict, Any, List, Optional, Tuple

from nonebot import logger, get_bot, require
from nonebot.adapters.onebot.v11 import Bot, MessageSegment
from nonebot.adapters.onebot.v11.exception import ActionFailed

from .database import TodoDatabase
from .time_parser import TimeParser

require("nonebot_plugin_apscheduler")
# 别名：本包 __init__.py 里 `scheduler` 这个名字已经绑给了 ReminderScheduler 实例
from nonebot_plugin_apscheduler import scheduler as aps_scheduler  # noqa: E402

#: 检查任务的 job id（全局唯一，便于在日志/WebUI 里定位）
TICK_JOB_ID = "todo_reminder_tick"
#: tick 迟到多少秒内仍然补跑。APScheduler 默认只给 1 秒，而一轮检查里有发消息的
#: 网络调用，必然超时——不显式放宽的话 tick 会被静默丢弃。
TICK_MISFIRE_GRACE = 30
#: 单条提醒的尝试次数上限（含首次投递）。失败也会计入 execution_count，
#: 达到上限即标记为 failed，不再重试。
MAX_ATTEMPTS = 3


class ReminderScheduler:
    """提醒调度器类"""
    
    def __init__(self, database: TodoDatabase, time_parser: TimeParser):
        self.database = database
        self.time_parser = time_parser
        self.check_interval = 60  # 检查间隔(秒)

    async def tick(self):
        """执行一轮检查（apscheduler 的 job 目标）

        异常自己吞掉：job 抛异常不会终止后续调度，但会在 apscheduler 日志里刷
        traceback，且与旧的「出错继续下一轮」语义不符。
        """
        try:
            await self._check_and_execute_reminders()
        except Exception as e:
            logger.error(f"提醒调度器错误: {e}")

    def is_running(self) -> bool:
        """任务是否已注册（供 main.is_scheduler_ready 判断）"""
        return aps_scheduler.get_job(TICK_JOB_ID) is not None

    def register_job(self) -> None:
        """把「一轮检查」注册成 APScheduler 的 interval job

        幂等（``replace_existing=True``），可以安全地被 on_startup 与 /todo 的
        兜底路径重复调用。本模块只在插件启用分支被 import，所以「禁用 ⇒ 不注册」
        自动成立；起停由 ``nonebot_plugin_apscheduler`` 接管。
        """
        aps_scheduler.add_job(
            self.tick,
            "interval",
            seconds=self.check_interval,
            # 启动即跑一次，保持旧循环「起来就先查一遍」的语义
            next_run_time=datetime.now(aps_scheduler.timezone),
            id=TICK_JOB_ID,
            replace_existing=True,
            misfire_grace_time=TICK_MISFIRE_GRACE,
            coalesce=True,
            max_instances=1,
        )
        logger.info(f"Todo提醒任务已注册: id={TICK_JOB_ID}, 每 {self.check_interval} 秒一次")

    async def _check_and_execute_reminders(self):
        """检查并执行到期的提醒"""
        try:
            current_time = datetime.now()

            # bot 取一次给两趟用：取不到就整轮跳过。
            # 注意：绝不能让「没有可用 bot」变成某条提醒的执行失败——那会白占
            # 重试次数、还会在离线期间每 tick 写一堆 failed 日志。
            try:
                bot = get_bot()
            except Exception as e:
                logger.warning(f"无法获取机器人实例，本轮提醒跳过: {e}")
                return

            # 1. 检查需要发送提前提醒的提醒
            await self._check_and_send_advance_reminders(bot, current_time)

            # 2. 获取待执行的提醒
            pending_reminders = await self.database.get_pending_reminders(limit=100)
            if not pending_reminders:
                return
            
            logger.info(f"检查到 {len(pending_reminders)} 个待执行提醒")
            
            for reminder in pending_reminders:
                try:
                    await self._execute_reminder(bot, reminder)
                except Exception as e:
                    logger.error(f"执行提醒失败 {reminder['id']}: {e}")
                    # 尝试重试失败的提醒
                    await self._handle_failed_reminder(reminder, str(e))
                    
        except Exception as e:
            logger.error(f"检查提醒时发生错误: {e}")
    
    async def _check_and_send_advance_reminders(self, bot: Bot, current_time: datetime):
        """检查并发送提前提醒"""
        try:
            # 获取需要发送提前提醒的提醒列表
            advance_reminders = await self.database.get_advance_reminders(current_time)
            if not advance_reminders:
                return
            
            logger.info(f"检查到 {len(advance_reminders)} 个需要发送提前提醒的提醒")
            
            for reminder in advance_reminders:
                try:
                    await self._send_advance_reminder(bot, reminder)
                    # 标记提前提醒已发送
                    await self.database.mark_advance_reminded(reminder['id'])
                    logger.info(f"提前提醒发送成功: {reminder['id']}")
                except Exception as e:
                    logger.error(f"发送提前提醒失败 {reminder['id']}: {e}")
                    
        except Exception as e:
            logger.error(f"检查提前提醒时发生错误: {e}")
    
    async def _send_advance_reminder(self, bot: Bot, reminder: Dict[str, Any]):
        """发送提前提醒"""
        try:
            # 构建提前提醒消息
            creator_user_id = int(reminder.get('user_id') or reminder.get('created_by'))
            creator_name = await self._get_creator_display_name(bot, reminder['group_id'], creator_user_id)
            message = self._build_advance_reminder_message(reminder, creator_name)
            
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
    
    async def _get_creator_display_name(self, bot: Bot, group_id: int, user_id: int) -> str:
        """获取创建者在群里的展示名：优先群名片，其次昵称，最后QQ号"""
        try:
            member = await bot.get_group_member_info(group_id=group_id, user_id=user_id)
            card = (member.get("card") or "").strip()
            nickname = (member.get("nickname") or "").strip()
            if card:
                return card
            if nickname:
                return nickname
        except Exception as e:
            logger.debug(f"获取成员展示名失败 user_id={user_id}, group_id={group_id}: {e}")
        return str(user_id)
    
    def _build_advance_reminder_message(self, reminder: Dict[str, Any], creator_name: str) -> str:
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
            message += f"创建者：{creator_name}\n"
            message += f"提醒ID：{reminder['id']}"
        elif reminder['target_user_id']:
            # @用户提前提醒格式
            message = f"提前提醒\n"
            message += f"还有 {advance_display} 就到时间了！\n"
            message += f"提醒时间：{remind_time_str}\n"
            message += f"内容：{reminder['content']}\n"
            message += f"创建者：{creator_name}\n"
            message += f"提醒ID：{reminder['id']}"
        else:
            # 普通提前提醒格式
            message = f"提前提醒\n"
            message += f"还有 {advance_display} 就到时间了！\n"
            message += f"提醒时间：{remind_time_str}\n"
            message += f"内容：{reminder['content']}\n"
            message += f"创建者：{creator_name}\n"
            message += f"提醒ID：{reminder['id']}"
        
        return message
    
    async def _handle_failed_reminder(self, reminder: Dict[str, Any], error_message: str):
        """处理失败的提醒，决定是否重试

        每次尝试（含失败）都会把 ``execution_count`` 原子 +1，所以它是「尝试次数」
        而不是「成功次数」；达到 :data:`MAX_ATTEMPTS` 就标记 failed、不再重试。
        """
        try:
            # 递增并取回自增后的值：计数必须在数据库里做，不能依赖本轮快照
            # （快照是这一轮开始时读的，失败路径下永远是旧值）
            attempts = await self.database.increment_execution_count(reminder['id'])

            if attempts < MAX_ATTEMPTS:
                # 还可以重试：保持 pending 状态，等待下次执行
                logger.info(
                    f"提醒 {reminder['id']} 执行失败，将重试 "
                    f"(第 {attempts}/{MAX_ATTEMPTS} 次)"
                )
            else:
                # 达到尝试上限，标记为失败（error_message 一并落库）
                logger.error(
                    f"提醒 {reminder['id']} 已尝试 {attempts} 次仍失败，标记为失败"
                )
                await self.database.update_reminder_status(
                    reminder['id'], 'failed', error_message
                )

            await self.database.log_reminder_execution(
                reminder['id'], 'failed', error_message, execution_duration=None
            )
        except Exception as e:
            logger.error(f"处理失败提醒时发生错误: {e}")
    
    async def _execute_reminder(self, bot: Bot, reminder: Dict[str, Any]):
        """执行单个提醒"""
        start_time = datetime.now()
        
        try:
            # 根据提醒类型发送消息
            if reminder['target_user_id'] == -1:
                # @全体成员提醒
                creator_user_id = int(reminder.get('user_id') or reminder.get('created_by'))
                creator_name = await self._get_creator_display_name(bot, reminder['group_id'], creator_user_id)
                message = self._build_reminder_message(reminder, creator_name, is_at_all=True)
                await self._send_group_at_all_reminder(bot, reminder, message)
            elif reminder['target_user_id']:
                # 指定用户提醒 - 发送到群组并@用户
                creator_user_id = int(reminder.get('user_id') or reminder.get('created_by'))
                creator_name = await self._get_creator_display_name(bot, reminder['group_id'], creator_user_id)
                message = self._build_reminder_message(reminder, creator_name, is_user_mention=True)
                await self._send_group_mention_reminder(bot, reminder, message)
            else:
                # 群组提醒 - 发送到群组
                creator_user_id = int(reminder.get('user_id') or reminder.get('created_by'))
                creator_name = await self._get_creator_display_name(bot, reminder['group_id'], creator_user_id)
                message = self._build_reminder_message(reminder, creator_name, is_user_mention=False)
                await self._send_group_reminder(bot, reminder, message)
            
            # 更新提醒状态为已完成
            await self.database.update_reminder_status(reminder['id'], 'completed')
            
            # 记录执行日志
            execution_duration = int((datetime.now() - start_time).total_seconds() * 1000)
            await self.database.log_reminder_execution(
                reminder['id'], 'success', execution_duration=execution_duration
            )
            
            logger.info(f"提醒执行成功: {reminder['id']}")
            
            # 如果是重复提醒，创建下一个提醒
            if reminder['remind_type'] in ['daily', 'weekly', 'monthly', 'workday']:
                await self._create_next_recurring_reminder(reminder)
                
        except Exception as e:
            logger.error(f"执行提醒失败: {e}")
            raise
    
    def _build_reminder_message(self, reminder: Dict[str, Any], creator_name: str, is_user_mention: bool = False, is_at_all: bool = False) -> str:
        """构建提醒消息"""
        remind_time_str = self.time_parser.format_remind_time(reminder['remind_time'])
        
        if is_at_all:
            # @全体成员提醒格式
            message = f"群组提醒通知\n"
            message += f"时间：{remind_time_str}\n"
            message += f"内容：{reminder['content']}\n"
            message += f"创建者：{creator_name}\n"
            message += f"提醒ID：{reminder['id']}"
        elif is_user_mention:
            # @用户提醒格式
            message = f"提醒通知\n"
            message += f"时间：{remind_time_str}\n"
            message += f"内容：{reminder['content']}\n"
            message += f"创建者：{creator_name}\n"
            message += f"提醒ID：{reminder['id']}"
        else:
            # 普通提醒格式
            message = f"提醒通知\n"
            message += f"时间：{remind_time_str}\n"
            message += f"内容：{reminder['content']}\n"
            message += f"创建者：{creator_name}\n"
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
    
    async def _check_bot_permission(self, bot: Bot, group_id: int) -> Tuple[bool, str]:
        """检查Bot是否有@全体成员的权限
        
        Returns:
            tuple[bool, str]: (是否有权限, 错误信息)
        """
        try:
            member_info = await bot.get_group_member_info(
                group_id=group_id,
                user_id=bot.self_id
            )
            bot_role = member_info.get('role', 'member')
            if bot_role not in ['owner', 'admin']:
                return False, f"Bot不是群主或管理员（当前角色：{bot_role}），无法@全体成员"
            return True, ""
        except Exception as e:
            logger.warning(f"检查Bot权限时出错: {e}")
            # 如果检查权限失败，仍然尝试发送，让平台返回具体错误
            return True, ""
    
    async def _send_group_at_all_reminder(self, bot: Bot, reminder: Dict[str, Any], message: str):
        """发送群组@全体成员提醒"""
        group_id = reminder['group_id']
        
        try:
            # 发送前检查Bot权限
            has_permission, error_msg = await self._check_bot_permission(bot, group_id)
            if not has_permission:
                logger.warning(f"提醒 {reminder['id']} @全体成员失败: {error_msg}")
                # 权限不足时，降级为普通群消息（不@全体成员）
                logger.info(f"提醒 {reminder['id']} 降级为普通群消息发送")
                fallback_message = f"[注意：Bot权限不足，无法@全体成员]\n{message}"
                await bot.send_group_msg(
                    group_id=group_id,
                    message=fallback_message
                )
                return
            
            # 构建@全体成员的消息
            at_all_message = MessageSegment.at("all") + "\n" + message
            await bot.send_group_msg(
                group_id=group_id,
                message=at_all_message
            )
            logger.info(f"提醒 {reminder['id']} @全体成员发送成功")
            
        except ActionFailed as e:
            # 处理NT-QQ特定的错误
            error_str = str(e)
            
            # 获取详细的错误信息
            retcode = getattr(e, 'retcode', None)
            error_info = getattr(e, 'info', None)
            error_message = getattr(e, 'message', '')
            error_wording = getattr(e, 'wording', '')
            
            # 记录详细的错误信息用于调试
            logger.warning(f"提醒 {reminder['id']} @全体成员失败详情: retcode={retcode}, info={error_info}, message={error_message}, wording={error_wording}, error_str={error_str}")
            
            # 检查是否是 121 错误（权限不足或频率限制）
            # 可能的情况：
            # 1. retcode == 121
            # 2. error_str 中包含 "121" 或 "result: 121" 或 "retcode: 121"
            # 3. error_message 或 error_wording 中包含相关的错误描述
            is_121_error = False
            error_detail = ""
            
            if retcode == 121:
                is_121_error = True
                error_detail = "权限不足或触发@全体成员频率限制"
            elif "121" in error_str or (error_info and "121" in str(error_info)):
                is_121_error = True
                error_detail = "权限不足或触发@全体成员频率限制（检测到错误码121）"
            elif any(keyword in error_str.lower() for keyword in ["@全体成员", "at all", "频率限制", "frequency", "权限不足", "permission"]):
                # 检查是否是与@全体成员相关的错误
                is_121_error = True
                error_detail = "@全体成员发送失败（可能是权限或频率限制）"
            
            if is_121_error:
                logger.warning(f"提醒 {reminder['id']} @全体成员失败 ({error_detail}): retcode={retcode}, error={error_str}")
                
                # 尝试降级为普通群消息
                try:
                    fallback_message = f"[注意：@全体成员失败（{error_detail}），已降级为普通消息]\n{message}"
                    await bot.send_group_msg(
                        group_id=group_id,
                        message=fallback_message
                    )
                    logger.info(f"提醒 {reminder['id']} 已降级为普通群消息发送")
                    return
                except Exception as fallback_error:
                    logger.error(f"提醒 {reminder['id']} 降级发送也失败: {fallback_error}")
                    # 如果降级发送也失败，抛出原始错误
                    raise ActionFailed(
                        status='failed',
                        retcode=1200,
                        data=None,
                        message=f"@全体成员失败（{error_detail}），且降级发送也失败",
                        wording=f"@全体成员失败（{error_detail}），且降级发送也失败",
                        echo=e.echo if hasattr(e, 'echo') else None
                    )
            else:
                # 其他 ActionFailed 错误，记录详细信息
                logger.error(f"提醒 {reminder['id']} @全体成员失败 (ActionFailed): retcode={retcode}, info={error_info}, message={error_message}, wording={error_wording}, error={error_str}")
                raise
                
        except Exception as e:
            logger.error(f"提醒 {reminder['id']} 发送群组@全体成员提醒失败: {e}")
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
            reminder_id = await self.database.create_reminder(new_reminder_data)
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
            reminder = await self.database.get_reminder(reminder_id)
            if not reminder:
                logger.error(f"提醒不存在: {reminder_id}")
                return False
            
            if reminder['status'] != 'pending':
                logger.warning(f"提醒状态不是pending: {reminder_id}")
                return False

            try:
                bot = get_bot()
            except Exception as e:
                logger.warning(f"无法获取机器人实例，立即执行取消: {e}")
                return False

            await self._execute_reminder(bot, reminder)
            return True
            
        except Exception as e:
            logger.error(f"立即执行提醒失败: {e}")
            return False
    
    async def cleanup_old_reminders(self, days: int = 30) -> int:
        """清理旧的已完成提醒"""
        try:
            cleaned_count = await self.database.cleanup_old_reminders(days)
            logger.info(f"清理了 {cleaned_count} 个旧提醒")
            return cleaned_count
        except Exception as e:
            logger.error(f"清理旧提醒失败: {e}")
            return 0
    
    def get_scheduler_status(self) -> Dict[str, Any]:
        """获取调度器状态（job 由 apscheduler 持有，这里只做只读映射）"""
        job = aps_scheduler.get_job(TICK_JOB_ID)
        return {
            "running": job is not None,
            "check_interval": self.check_interval,
            "task_running": job is not None,
            "job_id": TICK_JOB_ID,
        }

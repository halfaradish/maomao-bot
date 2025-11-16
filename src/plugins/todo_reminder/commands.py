"""
Todo提醒插件命令处理
"""

import re
from datetime import datetime
from typing import Dict, Any, List, Optional, Tuple

from nonebot import logger
from nonebot.adapters.onebot.v11 import Bot, Event, MessageSegment
from nonebot.adapters.onebot.v11.event import GroupMessageEvent, PrivateMessageEvent

from .database import TodoDatabase
from .time_parser import TimeParser
from .reminder_scheduler import ReminderScheduler
from .config import Config


class TodoCommands:
    """Todo命令处理类"""
    
    def __init__(self, database: TodoDatabase, time_parser: TimeParser, scheduler: ReminderScheduler, config: Config):
        self.database = database
        self.time_parser = time_parser
        self.scheduler = scheduler
        self.config = config
    
    async def _send_immediate_reminder(self, bot: Bot, event: Event, reminder_content: str, remind_type: str = "normal", target_user_id: Optional[int] = None) -> str:
        """发送立即提醒"""
        try:
            # 解析事件信息，获取发起人
            group_id, user_id, user_name = self._parse_event_info(event)
            
            # 构建消息，包含发起人信息
            message = f"【立即提醒】\n发起人: {user_name}\n{reminder_content}"
            
            if isinstance(event, GroupMessageEvent):
                group_id = event.group_id
                
                if remind_type == "at_all":
                    # @全体成员
                    try:
                        from nonebot.adapters.onebot.v11.exception import ActionFailed
                        # 检查权限
                        try:
                            member_info = await bot.get_group_member_info(
                                group_id=group_id,
                                user_id=bot.self_id
                            )
                            bot_role = member_info.get('role', 'member')
                            if bot_role not in ['owner', 'admin']:
                                # 权限不足，降级为普通消息
                                await bot.send_group_msg(group_id=group_id, message=message)
                                return f"立即提醒已发送（Bot权限不足，无法@全体成员）\n内容: {reminder_content}"
                        except:
                            pass
                        
                        # 构建@全体成员的消息
                        at_all_message = MessageSegment.at("all") + "\n" + message
                        await bot.send_group_msg(group_id=group_id, message=at_all_message)
                        return ""  # 不发送确认消息，避免冗余
                    except Exception as e:
                        # 如果@全体成员失败，降级为普通消息
                        logger.warning(f"@全体成员失败，降级为普通消息: {e}")
                        await bot.send_group_msg(group_id=group_id, message=message)
                        return f"立即提醒已发送（@全体成员失败，已降级为普通消息）\n内容: {reminder_content}"
                
                elif remind_type == "at_user" and target_user_id:
                    # @指定用户
                    mention_message = MessageSegment.at(target_user_id) + "\n" + message
                    await bot.send_group_msg(group_id=group_id, message=mention_message)
                    return ""  # 不发送确认消息，避免冗余
                
                elif remind_type == "at_self" and target_user_id:
                    # @自己
                    mention_message = MessageSegment.at(target_user_id) + "\n" + message
                    await bot.send_group_msg(group_id=group_id, message=mention_message)
                    return ""  # 不发送确认消息，避免冗余
                
                else:
                    # 普通群消息
                    await bot.send_group_msg(group_id=group_id, message=message)
                    return ""  # 不发送确认消息，避免冗余
            else:
                # 私聊消息
                await bot.send_private_msg(user_id=event.user_id, message=message)
                return ""  # 不发送确认消息，避免冗余
                
        except Exception as e:
            logger.error(f"发送立即提醒失败: {e}")
            return f"立即提醒发送失败: {str(e)}"
    
    async def create_todo(self, bot: Bot, event: Event, content: str) -> str:
        """创建todo"""
        try:
            # 解析事件信息
            group_id, user_id, user_name = self._parse_event_info(event)
            if not user_id:
                return "无法获取用户信息"
            
            # 私聊场景下，group_id 可以为 None，使用特殊值 -1 表示个人提醒
            if group_id is None:
                group_id = -1
            
            # 解析时间和内容
            time_str, advance_str, reminder_content = self._parse_reminder_content(content)
            logger.debug(f"create_todo: content={repr(content)}, time_str={repr(time_str)}, advance_str={repr(advance_str)}, reminder_content={repr(reminder_content)}")
            if not time_str or not reminder_content:
                logger.warning(f"create_todo: 解析失败, content={repr(content)}, time_str={repr(time_str)}, reminder_content={repr(reminder_content)}")
                return "请提供正确的时间格式，例如：todo 30分钟后 开会 或 todo 2小时后 -30min 开会"
            
            # 解析时间
            time_result = self.time_parser.parse_time_with_advance(time_str, advance_str)
            if not time_result:
                logger.warning(f"create_todo: 时间解析失败, time_str={repr(time_str)}")
                return f"无法解析时间格式：{time_str}"
            
            # 检查是否是立即提醒
            if time_result.get('remind_type') == 'immediate':
                return await self._send_immediate_reminder(bot, event, reminder_content, "normal")
            
            # 创建todo数据
            reminder_data = {
                'group_id': group_id,
                'user_id': user_id,
                'target_user_id': None,
                'content': reminder_content,
                'remind_time': time_result['remind_time'],
                'remind_type': time_result['remind_type'],
                'status': 'pending',
                'created_by': user_name,
                'last_modified_by': user_name,
                'advance_remind_minutes': time_result.get('advance_remind_minutes', 0),
                'advance_reminded': False
            }
            
            # 保存到数据库
            reminder_id = await self.database.create_reminder(reminder_data)
            
            # 格式化时间显示
            time_display = self.time_parser.format_remind_time(time_result['remind_time'])
            
            # 构建返回消息
            remind_type = time_result.get('remind_type', 'once')
            message = f"todo创建成功！\nID: {reminder_id}\n时间: {time_display}\n内容: {reminder_content}"
            
            # 如果是重复提醒，添加重复类型信息
            if remind_type in ['daily', 'weekly', 'monthly', 'workday']:
                repeat_names = {
                    'daily': '每天重复',
                    'weekly': '每周重复',
                    'monthly': '每月重复',
                    'workday': '工作日重复'
                }
                message += f"\n类型: {repeat_names.get(remind_type, '重复提醒')}"
            
            # 如果有提前提醒，添加提前提醒信息
            if time_result.get('advance_remind_minutes', 0) > 0:
                advance_minutes = time_result['advance_remind_minutes']
                advance_display = self._format_advance_time(advance_minutes)
                message += f"\n提前提醒: {advance_display}"
            
            return message
            
        except Exception as e:
            logger.error(f"创建todo失败: {e}")
            return f"创建todo失败: {str(e)}"
    
    
    async def create_group_todo(self, bot: Bot, event: Event, content: str) -> str:
        """创建群组todo"""
        try:
            # 解析事件信息
            group_id, user_id, user_name = self._parse_event_info(event)
            if not user_id:
                return "无法获取用户信息"
            
            # 群组todo必须在群聊中创建
            if not group_id:
                return "群组todo只能在群聊中创建"
            
            # 解析时间和内容
            time_str, advance_str, reminder_content = self._parse_reminder_content(content)
            if not time_str or not reminder_content:
                return "请提供正确的时间格式，例如：群todo 30分钟后 开会 或 群todo 2小时后 -15min 开会"
            
            # 解析时间
            time_result = self.time_parser.parse_time_with_advance(time_str, advance_str)
            if not time_result:
                return f"无法解析时间格式：{time_str}"
            
            # 创建todo数据
            reminder_data = {
                'group_id': group_id,
                'user_id': user_id,
                'target_user_id': None,  # 群组todo
                'content': reminder_content,
                'remind_time': time_result['remind_time'],
                'remind_type': time_result['remind_type'],
                'status': 'pending',
                'created_by': user_name,
                'last_modified_by': user_name,
                'advance_remind_minutes': time_result.get('advance_remind_minutes', 0),
                'advance_reminded': False
            }
            
            # 保存到数据库
            reminder_id = await self.database.create_reminder(reminder_data)
            
            # 格式化时间显示
            time_display = self.time_parser.format_remind_time(time_result['remind_time'])
            
            # 构建返回消息
            remind_type = time_result.get('remind_type', 'once')
            message = f"群组todo创建成功！\nID: {reminder_id}\n时间: {time_display}\n内容: {reminder_content}"
            
            # 如果是重复提醒，添加重复类型信息
            if remind_type in ['daily', 'weekly', 'monthly', 'workday']:
                repeat_names = {
                    'daily': '每天重复',
                    'weekly': '每周重复',
                    'monthly': '每月重复',
                    'workday': '工作日重复'
                }
                message += f"\n类型: {repeat_names.get(remind_type, '重复提醒')}"
            
            # 如果有提前提醒，添加提前提醒信息
            if time_result.get('advance_remind_minutes', 0) > 0:
                advance_minutes = time_result['advance_remind_minutes']
                advance_display = self._format_advance_time(advance_minutes)
                message += f"\n提前提醒: {advance_display}"
            
            return message
            
        except Exception as e:
            logger.error(f"创建群组todo失败: {e}")
            return f"创建群组todo失败: {str(e)}"
    
    async def list_my_todos(self, bot: Bot, event: Event) -> str:
        """列出群组todo列表（群内所有用户共享）"""
        try:
            # 解析事件信息
            group_id, user_id, user_name = self._parse_event_info(event)
            if not user_id:
                return "无法获取用户信息"
            
            # 私聊场景下使用特殊值
            if group_id is None:
                group_id = -1
            
            # 获取群组todo列表（群内所有用户共享）
            reminders = await self.database.get_group_shared_reminders(group_id, 'pending')
            if not reminders:
                return "暂无待办事项"
            
            # 构建消息
            message = "群组todo列表:\n"
            for reminder in reminders:
                time_display = self.time_parser.format_remind_time(reminder['remind_time'])
                creator_name = reminder.get('created_by', '未知用户')
                message += f"ID {reminder['id']} | {time_display} | {reminder['content']} | 创建者: {creator_name}\n"
            
            return message
            
        except Exception as e:
            logger.error(f"获取todo列表失败: {e}")
            return f"获取todo列表失败: {str(e)}"
    
    async def list_completed_todos(self, bot: Bot, event: Event) -> str:
        """列出已完成的群组todo（群内所有用户共享）"""
        try:
            # 解析事件信息
            group_id, user_id, user_name = self._parse_event_info(event)
            if not user_id:
                return "无法获取用户信息"
            
            # 私聊场景下使用特殊值
            if group_id is None:
                group_id = -1
            
            # 获取群组已完成的todo列表（群内所有用户共享）
            reminders = await self.database.get_group_shared_reminders(group_id, 'completed')
            if not reminders:
                return "暂无已完成的todo事项"
            
            # 构建消息
            message = "群组已完成的todo列表:\n"
            for reminder in reminders:
                time_display = self.time_parser.format_remind_time(reminder['remind_time'])
                creator_name = reminder.get('created_by', '未知用户')
                completed_time = reminder.get('completed_time', '')
                if completed_time:
                    completed_display = datetime.fromisoformat(completed_time).strftime('%Y-%m-%d %H:%M')
                    message += f"ID {reminder['id']} | {time_display} | 完成于 {completed_display} | {reminder['content']} | 创建者: {creator_name}\n"
                else:
                    message += f"ID {reminder['id']} | {time_display} | {reminder['content']} | 创建者: {creator_name}\n"
            
            return message
            
        except Exception as e:
            logger.error(f"获取已完成todo列表失败: {e}")
            return f"获取已完成todo列表失败: {str(e)}"
    
    async def list_group_reminders(self, bot: Bot, event: Event) -> str:
        """列出群组todo"""
        try:
            # 解析事件信息
            group_id, user_id, user_name = self._parse_event_info(event)
            if not group_id:
                return "无法获取群组信息"
            
            # 获取群组todo列表
            reminders = await self.database.get_group_reminders(group_id, 'pending')
            if not reminders:
                return "群组暂无待办事项"
            
            # 构建消息
            message = "群组todo列表:\n"
            for reminder in reminders:
                time_display = self.time_parser.format_remind_time(reminder['remind_time'])
                if reminder['target_user_id'] == -1:
                    target_info = "@全体成员"
                else:
                    target_info = "群组todo"
                message += f"ID {reminder['id']} | {time_display} | {target_info} | {reminder['content']}\n"
            
            return message
            
        except Exception as e:
            logger.error(f"获取群组todo列表失败: {e}")
            return f"获取群组todo列表失败: {str(e)}"
    
    async def cancel_todo(self, bot: Bot, event: Event, todo_id: str) -> str:
        """取消群组todo（群内任何用户都可以取消）"""
        try:
            # 解析事件信息
            group_id, user_id, user_name = self._parse_event_info(event)
            if not user_id:
                return "无法获取用户信息"
            
            # 私聊场景下使用特殊值
            current_group_id = group_id if group_id is not None else -1
            
            # 验证todoID
            try:
                reminder_id_int = int(todo_id)
            except ValueError:
                return "todoID格式错误"
            
            # 获取todo信息
            reminder = await self.database.get_reminder(reminder_id_int)
            if not reminder:
                return "todo不存在"
            
            # 检查群组权限（只允许取消同群的todo）
            if reminder['group_id'] != current_group_id:
                return "只能取消本群的todo"
            
            if reminder['status'] != 'pending':
                return f"todo状态为{reminder['status']}，无法取消"
            
            # 更新状态
            success = await self.database.update_reminder_status(reminder_id_int, 'cancelled')
            if success:
                return f"todo {todo_id} 已取消"
            else:
                return "取消todo失败"
                
        except Exception as e:
            logger.error(f"取消todo失败: {e}")
            return f"取消todo失败: {str(e)}"
    
    async def complete_todo(self, bot: Bot, event: Event, todo_id: str) -> str:
        """完成群组todo（群内任何用户都可以完成）"""
        try:
            # 解析事件信息
            group_id, user_id, user_name = self._parse_event_info(event)
            if not user_id:
                return "无法获取用户信息"
            
            # 私聊场景下使用特殊值
            current_group_id = group_id if group_id is not None else -1
            
            # 验证todoID
            try:
                reminder_id_int = int(todo_id)
            except ValueError:
                return "todoID格式错误"
            
            # 获取todo信息
            reminder = await self.database.get_reminder(reminder_id_int)
            if not reminder:
                return "todo不存在"
            
            # 检查群组权限（只允许完成同群的todo）
            if reminder['group_id'] != current_group_id:
                return "只能完成本群的todo"
            
            if reminder['status'] != 'pending':
                return f"todo状态为{reminder['status']}，无法完成"
            
            # 更新状态
            success = await self.database.update_reminder_status(reminder_id_int, 'completed')
            if success:
                return f"todo {todo_id} 已标记为完成"
            else:
                return "完成todo失败"
                
        except Exception as e:
            logger.error(f"完成todo失败: {e}")
            return f"完成todo失败: {str(e)}"
    
    async def delete_todo(self, bot: Bot, event: Event, todo_id: str) -> str:
        """删除群组todo（群内任何用户都可以删除）"""
        try:
            # 解析事件信息
            group_id, user_id, user_name = self._parse_event_info(event)
            if not user_id:
                return "无法获取用户信息"
            
            # 私聊场景下使用特殊值
            current_group_id = group_id if group_id is not None else -1
            
            # 验证todoID
            try:
                reminder_id_int = int(todo_id)
            except ValueError:
                return "todoID格式错误"
            
            # 获取todo信息检查群组权限
            reminder = await self.database.get_reminder(reminder_id_int)
            if not reminder:
                return "todo不存在"
            
            # 检查群组权限（只允许删除同群的todo）
            if reminder['group_id'] != current_group_id:
                return "只能删除本群的todo"
            
            # 删除群组共享todo
            success = await self.database.delete_group_shared_reminder(reminder_id_int, current_group_id)
            if success:
                return f"todo {todo_id} 已删除"
            else:
                return "删除todo失败"
                
        except Exception as e:
            logger.error(f"删除todo失败: {e}")
            return f"删除todo失败: {str(e)}"
    
    async def get_todo_info(self, bot: Bot, event: Event, todo_id: str) -> str:
        """获取todo详情"""
        try:
            # 验证todoID
            try:
                reminder_id_int = int(todo_id)
            except ValueError:
                return "todoID格式错误"
            
            # 获取todo信息
            reminder = await self.database.get_reminder(reminder_id_int)
            if not reminder:
                return "todo不存在"
            
            # 构建详情消息
            time_display = self.time_parser.format_remind_time(reminder['remind_time'])
            if reminder['target_user_id'] == -1:
                target_info = "@全体成员"
            else:
                target_info = "群组todo"
            
            message = f"todo详情:\n"
            message += f"ID: {reminder['id']}\n"
            message += f"时间: {time_display}\n"
            message += f"内容: {reminder['content']}\n"
            message += f"目标: {target_info}\n"
            message += f"类型: {reminder['remind_type']}\n"
            message += f"状态: {reminder['status']}\n"
            message += f"创建者: {reminder['created_by']}\n"
            message += f"创建时间: {reminder['created_at']}"
            
            return message
            
        except Exception as e:
            logger.error(f"获取todo详情失败: {e}")
            return f"获取todo详情失败: {str(e)}"
    
    
    def _format_advance_time(self, advance_minutes: int) -> str:
        """格式化提前提醒时间显示（支持天、小时、分钟）"""
        if advance_minutes < 60:
            return f"{advance_minutes}分钟"
        
        # 计算天、小时、分钟
        total_minutes = advance_minutes
        days = total_minutes // (24 * 60)
        remaining_minutes = total_minutes % (24 * 60)
        hours = remaining_minutes // 60
        minutes = remaining_minutes % 60
        
        parts = []
        if days > 0:
            parts.append(f"{days}天")
        if hours > 0:
            parts.append(f"{hours}小时")
        if minutes > 0:
            parts.append(f"{minutes}分钟")
        
        return "".join(parts)
    
    def _parse_event_info(self, event: Event) -> Tuple[Optional[int], Optional[int], str]:
        """解析事件信息"""
        try:
            group_id = None
            user_id = None
            user_name = "未知用户"
            
            if isinstance(event, GroupMessageEvent):
                group_id = event.group_id
                user_id = event.user_id
                user_name = event.sender.card or event.sender.nickname or "未知用户"
            elif isinstance(event, PrivateMessageEvent):
                user_id = event.user_id
                user_name = event.sender.nickname or "未知用户"
            
            return group_id, user_id, user_name
        except Exception as e:
            logger.error(f"解析事件信息失败: {e}")
            return None, None, "未知用户"
    
    def _parse_reminder_content(self, content: str) -> Tuple[Optional[str], Optional[str], Optional[str]]:
        """解析todo内容，提取时间、提前时间和内容"""
        # 匹配格式：todo [我|自己] 时间 [-提前时间] 内容
        # 支持格式：
        # 1. todo 时间 内容 (无提前时间)
        # 2. todo 时间 -提前时间 内容 (有提前时间，以-开头)
        # 3. todo 我 时间 内容 (@自己的提醒，无提前时间)
        # 4. todo 我 时间 -提前时间 内容 (@自己的提醒，有提前时间)
        
        content = content.strip()
        
        # 先尝试匹配带提前时间的格式（提前时间以-开头）
        pattern_with_advance = r'^todo\s+(?:我|自己)?\s*(.+?)\s+(-.+?)\s+(.+)$'
        match_with_advance = re.match(pattern_with_advance, content)
        
        if match_with_advance:
            time_str = match_with_advance.group(1).strip()
            advance_str = match_with_advance.group(2).strip()
            reminder_content = match_with_advance.group(3).strip()
            
            # 检查提前时间字符串是否有效
            advance_minutes = self.time_parser.parse_advance_time(advance_str)
            if advance_minutes is not None:
                return time_str, advance_str, reminder_content
        
        # 如果没有提前时间或解析失败，尝试普通格式（支持"我"关键字）
        pattern_normal = r'^todo\s+(?:我|自己)?\s*(.+?)\s+(.+)$'
        match_normal = re.match(pattern_normal, content)
        
        if match_normal:
            time_str = match_normal.group(1).strip()
            reminder_content = match_normal.group(2).strip()
            logger.debug(f"_parse_reminder_content: 匹配成功, content={repr(content)}, time_str={repr(time_str)}, reminder_content={repr(reminder_content)}")
            return time_str, None, reminder_content
        
        logger.warning(f"_parse_reminder_content: 正则匹配失败, content={repr(content)}, pattern_normal={pattern_normal}")
        return None, None, None
    
    
    async def show_time_formats(self, bot: Bot, event: Event) -> str:
        """显示支持的时间格式"""
        return """支持的时间格式：

 立即提醒：
• 现在/立刻/立即/now (立即执行提醒)

 相对时间（一次性提醒）：
• X天Y小时Z分钟后 (如：3天5小时45分钟后)
• X天Y小时后 (如：2天3小时后)
• X天后 (如：3天后)
• X小时Y分钟后 (如：5小时45分钟后)
• X小时后 (如：2小时后)
• X分钟后 (如：30分钟后)

 当天时间点（一次性提醒）：
• X小时Y分 (如：5小时40分，表示当天5点40分，如果已过则为明天)

 周几时间（一次性提醒）：
• 周X点 (如：周一9点，等同于周一9:00，仅本周一次性提醒，支持一二三四五六日天)
• 周X点Y分 (如：周一9点30分，仅本周一次性提醒)
• 周X:Y (如：周一9:30，仅本周一次性提醒，支持冒号格式)
• 下周X点 (如：下周一9:00，仅下周一次性提醒，支持一二三四五六日天)
• 下周X点Y分 (如：下周一9点30分，仅下周一次性提醒)
• 下周X:Y (如：下周一9:30，仅下周一次性提醒，支持冒号格式)

 具体日期时间（一次性提醒）：
• X月X日-X点-X分 (如：1月15日-9点-30分，当年，如果已过则为明年)
• X月X日-X点 (如：1月15日-9点，等同于1月15日-9点-0分，当年，如果已过则为明年)
• X-X-X-X (如：2-5-8-30，表示2月5日8点30分，当年，如果已过则为明年)
• X-X-X (如：2-5-8，表示2月5日8点，等同于2月5日8点0分，当年，如果已过则为明年)

 重复提醒：
• 每天X点 (如：每天9点，每天重复)
• 每天X点X分 (如：每天9点30分，每天重复)
• 工作日X点 (如：工作日8点，工作日重复，跳过周末)
• 工作日X点X分 (如：工作日8点30分，工作日重复)
• 每周X点 (如：每周一10点，每周的指定星期重复，支持一二三四五六日天)
• 每周X点X分 (如：每周一10点30分，每周的指定星期重复)
• 每月X号X点 (如：每月1号9点，每月的指定日期重复)
• 每月X号X点X分 (如：每月1号9点30分，每月的指定日期重复)

 提前提醒：
• 支持在时间后添加提前时间参数
• 格式：-Xmin, -Xh, -Xd (如：-30min, -2h, -1d)
• 也可以使用中文：-X分钟, -X小时, -X天

 使用示例：
• todo 现在 提醒我喝水 (立即提醒)
• todo 我 现在 提醒内容 (@自己，立即提醒)
• todo 群提醒 现在 提醒内容 (@全体成员，立即提醒)
• todo @用户 现在 提醒内容 (@用户，立即提醒)
• todo 3天5小时45分钟后 重要会议
• todo 2天3小时后 重要会议
• todo 3天后 重要会议
• todo 5小时45分钟后 重要会议
• todo 5小时40分 当天会议 (当天5点40分)
• todo 30分钟后 提醒我休息
• todo 2小时后 开会
• todo 周一9点 周会
• todo 周一9:30 周会
• todo 下周一九点 重要会议
• todo 1月15日-9点-30分 会议
• todo 2-5-8-30 会议 (2月5日8点30分)
• todo 每天9点 每日打卡
• todo 工作日8点 上班提醒
• todo 每周一10点 周会
• todo 每月1号9点 月度会议
• todo 30分钟后 -15min 提醒我休息 (提前15分钟提醒)"""


    async def create_group_at_all_todo(self, bot: Bot, event: Event, content: str) -> str:
        """创建群组@全体成员todo"""
        try:
            # 解析事件信息
            group_id, user_id, user_name = self._parse_event_info(event)
            if not user_id:
                return "无法获取用户信息"
            
            # 群组@全体成员提醒必须在群聊中创建
            if not group_id:
                return "群组@全体成员提醒只能在群聊中创建"
            
            # 解析时间和内容
            time_str, advance_str, reminder_content = self._parse_reminder_content(content)
            if not time_str or not reminder_content:
                return "请提供正确的时间格式，例如：群提醒 30分钟后 开会 或 群提醒 现在 提醒内容"
            
            # 解析时间
            time_result = self.time_parser.parse_time_with_advance(time_str, advance_str)
            if not time_result:
                return f"无法解析时间格式：{time_str}"
            
            # 检查是否是立即提醒
            if time_result.get('remind_type') == 'immediate':
                return await self._send_immediate_reminder(bot, event, reminder_content, "at_all")
            
            # 创建todo数据，使用特殊标记表示@全体成员
            reminder_data = {
                'group_id': group_id,
                'user_id': user_id,
                'target_user_id': -1,  # 使用-1表示@全体成员
                'content': reminder_content,
                'remind_time': time_result['remind_time'],
                'remind_type': time_result['remind_type'],
                'status': 'pending',
                'created_by': user_name,
                'last_modified_by': user_name,
                'advance_remind_minutes': time_result.get('advance_remind_minutes', 0),
                'advance_reminded': False
            }
            
            # 保存到数据库
            reminder_id = await self.database.create_reminder(reminder_data)
            
            # 格式化时间显示
            time_display = self.time_parser.format_remind_time(time_result['remind_time'])
            
            # 构建返回消息
            remind_type = time_result.get('remind_type', 'once')
            message = f"群组@全体成员todo创建成功！\nID: {reminder_id}\n时间: {time_display}\n内容: {reminder_content}"
            
            # 如果是重复提醒，添加重复类型信息
            if remind_type in ['daily', 'weekly', 'monthly', 'workday']:
                repeat_names = {
                    'daily': '每天重复',
                    'weekly': '每周重复',
                    'monthly': '每月重复',
                    'workday': '工作日重复'
                }
                message += f"\n类型: {repeat_names.get(remind_type, '重复提醒')}"
            
            # 如果有提前提醒，添加提前提醒信息
            if time_result.get('advance_remind_minutes', 0) > 0:
                advance_minutes = time_result['advance_remind_minutes']
                advance_display = self._format_advance_time(advance_minutes)
                message += f"\n提前提醒: {advance_display}"
            
            return message
            
        except Exception as e:
            logger.error(f"创建群组@全体成员todo失败: {e}")
            return f"创建群组@全体成员todo失败: {str(e)}"

    async def create_user_mention_todo(self, bot: Bot, event: GroupMessageEvent, content: str) -> str:
        """创建@用户提醒"""
        try:
            # 解析事件信息
            group_id = event.group_id
            user_id = event.user_id
            user_name = event.sender.card or event.sender.nickname or "未知用户"
            
            # 获取消息对象
            message = event.get_message()
            
            # 提取@的用户
            at_users = []
            text_parts = []
            
            for segment in message:
                if segment.type == "at":
                    qq = segment.data.get("qq")
                    if qq:
                        at_users.append(int(qq))
                elif segment.type == "text":
                    text_parts.append(segment.data.get("text", ""))
            
            if not at_users:
                return "请@要提醒的用户，例如：@张三 30分钟后 开会"
            
            # 获取第一个@的用户（暂时只支持@一个用户）
            target_user_id = at_users[0]
            
            # 合并文本内容
            text_content = " ".join(text_parts).strip()
            
            if not text_content:
                return "请提供时间和内容，例如：@用户 30分钟后 开会"
            
            # 去掉可能存在的 "todo " 前缀（因为从消息中提取的文本可能包含命令前缀）
            text_content = text_content.lstrip("todo ").strip()
            
            if not text_content:
                return "请提供时间和内容，例如：@用户 30分钟后 开会"
            
            # 获取目标用户信息
            try:
                target_user_info = await bot.get_stranger_info(user_id=target_user_id)
                target_user_name = target_user_info.get("nickname", "未知用户")
            except Exception as e:
                logger.error(f"获取用户信息失败 (QQ:{target_user_id}): {e}")
                target_user_name = f"用户{target_user_id}"
            
            # 解析时间和内容
            # 格式：todo 时间 [提前时间] 内容
            # 添加 "todo " 前缀以符合解析器期望的格式
            parsed = self._parse_reminder_content(f"todo {text_content}")
            if not parsed:
                return "请提供正确的时间格式，例如：@用户 30分钟后 开会"
            
            time_str, advance_str, reminder_content = parsed
            if not time_str or not reminder_content:
                return "请提供时间和内容，例如：@用户 30分钟后 开会"
            
            # 解析时间
            time_result = self.time_parser.parse_time_with_advance(time_str, advance_str)
            if not time_result:
                return f"无法解析时间格式：{time_str}"
            
            # 检查是否是立即提醒
            if time_result.get('remind_type') == 'immediate':
                return await self._send_immediate_reminder(bot, event, reminder_content, "at_user", target_user_id)
            
            # 创建todo数据
            reminder_data = {
                'group_id': group_id,
                'user_id': user_id,
                'target_user_id': target_user_id,  # 指定@的用户
                'content': reminder_content,
                'remind_time': time_result['remind_time'],
                'remind_type': time_result['remind_type'],
                'status': 'pending',
                'created_by': user_name,
                'last_modified_by': user_name,
                'advance_remind_minutes': time_result.get('advance_remind_minutes', 0),
                'advance_reminded': False
            }
            
            # 保存到数据库
            reminder_id = await self.database.create_reminder(reminder_data)
            
            # 格式化时间显示
            time_display = self.time_parser.format_remind_time(time_result['remind_time'])
            
            # 构建返回消息
            remind_type = time_result.get('remind_type', 'once')
            message = f"@用户提醒创建成功！\nID: {reminder_id}\n提醒对象: {target_user_name}\n时间: {time_display}\n内容: {reminder_content}"
            
            # 如果是重复提醒，添加重复类型信息
            if remind_type in ['daily', 'weekly', 'monthly', 'workday']:
                repeat_names = {
                    'daily': '每天重复',
                    'weekly': '每周重复',
                    'monthly': '每月重复',
                    'workday': '工作日重复'
                }
                message += f"\n类型: {repeat_names.get(remind_type, '重复提醒')}"
            
            # 如果有提前提醒，添加提前提醒信息
            if time_result.get('advance_remind_minutes', 0) > 0:
                advance_minutes = time_result['advance_remind_minutes']
                advance_display = self._format_advance_time(advance_minutes)
                message += f"\n提前提醒: {advance_display}"
            
            return message
            
        except Exception as e:
            logger.error(f"创建@用户提醒失败: {e}")
            import traceback
            logger.error(f"错误堆栈: {traceback.format_exc()}")
            return f"创建@用户提醒失败: {str(e)}"

    def _extract_at_users(self, message) -> List[int]:
        """从消息中提取@的用户QQ号"""
        at_users = []
        try:
            at_segments = message.get("at", [])
            for at_seg in at_segments:
                qq = at_seg.data.get("qq")
                if qq:
                    at_users.append(int(qq))
        except Exception as e:
            logger.error(f"提取@用户失败: {e}")
        return at_users

    async def create_self_mention_todo(self, bot: Bot, event: Event, content: str) -> str:
        """创建@自己的提醒"""
        try:
            # 解析事件信息
            group_id, user_id, user_name = self._parse_event_info(event)
            if not user_id:
                return "无法获取用户信息"
            
            # @自己的提醒必须在群聊中创建
            if not group_id:
                return "@自己的提醒只能在群聊中使用"
            
            # 解析时间和内容
            time_str, advance_str, reminder_content = self._parse_reminder_content(content)
            logger.debug(f"解析结果: time_str={time_str}, advance_str={advance_str}, reminder_content={reminder_content}")
            if not time_str or not reminder_content:
                return "请提供正确的时间格式，例如：todo 我 2分钟后 吃饭"
            
            # 解析时间
            logger.debug(f"正在解析时间: time_str={time_str}, advance_str={advance_str}")
            time_result = self.time_parser.parse_time_with_advance(time_str, advance_str)
            if not time_result:
                logger.warning(f"无法解析时间格式: time_str={time_str}, advance_str={advance_str}, content={content}")
                return f"无法解析时间格式：{time_str}"
            
            # 检查是否是立即提醒
            if time_result.get('remind_type') == 'immediate':
                return await self._send_immediate_reminder(bot, event, reminder_content, "at_self", user_id)
            
            # 创建todo数据，target_user_id设为自己的user_id
            reminder_data = {
                'group_id': group_id,
                'user_id': user_id,
                'target_user_id': user_id,  # @自己
                'content': reminder_content,
                'remind_time': time_result['remind_time'],
                'remind_type': time_result['remind_type'],
                'status': 'pending',
                'created_by': user_name,
                'last_modified_by': user_name,
                'advance_remind_minutes': time_result.get('advance_remind_minutes', 0),
                'advance_reminded': False
            }
            
            # 保存到数据库
            reminder_id = await self.database.create_reminder(reminder_data)
            
            # 格式化时间显示
            time_display = self.time_parser.format_remind_time(time_result['remind_time'])
            
            # 构建返回消息
            remind_type = time_result.get('remind_type', 'once')
            message = f"@自己的提醒创建成功！\nID: {reminder_id}\n时间: {time_display}\n内容: {reminder_content}"
            
            # 如果是重复提醒，添加重复类型信息
            if remind_type in ['daily', 'weekly', 'monthly', 'workday']:
                repeat_names = {
                    'daily': '每天重复',
                    'weekly': '每周重复',
                    'monthly': '每月重复',
                    'workday': '工作日重复'
                }
                message += f"\n类型: {repeat_names.get(remind_type, '重复提醒')}"
            
            # 如果有提前提醒，添加提前提醒信息
            if time_result.get('advance_remind_minutes', 0) > 0:
                advance_minutes = time_result['advance_remind_minutes']
                advance_display = self._format_advance_time(advance_minutes)
                message += f"\n提前提醒: {advance_display}"
            
            return message
            
        except Exception as e:
            logger.error(f"创建@自己的提醒失败: {e}")
            return f"创建@自己的提醒失败: {str(e)}"

    async def create_immediate_todo(self, bot: Bot, event: Event, content: str) -> str:
        """创建并立即执行提醒"""
        try:
            # 解析事件信息
            group_id, user_id, user_name = self._parse_event_info(event)
            if not user_id:
                return "无法获取用户信息"
            
            # 解析内容（"现在"命令不需要时间，只需要内容）
            reminder_content = content.strip()
            if not reminder_content:
                return "请提供提醒内容，例如：todo 现在 提醒我喝水"
            
            # 直接发送提醒消息（不通过数据库和调度器）
            message = f"【立即提醒】\n发起人: {user_name}\n{reminder_content}"
            
            try:
                # 根据事件类型发送消息
                if isinstance(event, GroupMessageEvent):
                    # 群聊中发送群消息
                    await bot.send_group_msg(group_id=event.group_id, message=message)
                else:
                    # 私聊中发送私聊消息
                    await bot.send_private_msg(user_id=event.user_id, message=message)
                
                return ""
            except Exception as send_error:
                logger.error(f"发送立即提醒失败: {send_error}")
                return f"立即提醒发送失败: {str(send_error)}"
            
        except Exception as e:
            logger.error(f"创建立即提醒失败: {e}")
            return f"创建立即提醒失败: {str(e)}"



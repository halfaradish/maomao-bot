"""
全员确认提醒调度器
负责定时检查未确认的消息并发送提醒
"""
from __future__ import annotations

import asyncio
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional

from nonebot import get_bot, logger
from nonebot.adapters.onebot.v11 import Bot

from . import database
from ...common.django_crud import async_get_many, init_django_if_needed

init_django_if_needed()

from botdb.models import QQMessageReceiptSummary, QQRobotMessage, beijing_now


class AckReminderScheduler:
    """全员确认提醒调度器"""
    
    # 提醒配置：每个阶段的提醒间隔（分钟）
    REMINDER_INTERVALS = [5, 15, 30]  # 5分钟后第一次提醒，15分钟后第二次，30分钟后第三次
    MAX_REMINDER_STAGE = len(REMINDER_INTERVALS)  # 最多提醒3次
    
    def __init__(self):
        self.running = False
        self.task: Optional[asyncio.Task] = None
        self.check_interval = 60  # 检查间隔(秒)，每分钟检查一次
    
    async def start(self):
        """启动调度器"""
        if self.running:
            logger.warning("全员确认提醒调度器已在运行")
            return
        
        self.running = True
        self.task = asyncio.create_task(self._scheduler_loop())
        logger.info("全员确认提醒调度器已启动")
    
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
        
        logger.info("全员确认提醒调度器已停止")
    
    async def _scheduler_loop(self):
        """调度器主循环"""
        while self.running:
            try:
                await self._check_and_send_reminders()
                await asyncio.sleep(self.check_interval)
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"全员确认提醒调度器错误: {e}", exc_info=True)
                await asyncio.sleep(self.check_interval)
    
    async def _check_and_send_reminders(self):
        """检查并发送到期的提醒"""
        try:
            now = beijing_now()
            
            # 查找需要提醒的消息
            # 条件：next_reminder_at <= now 且 未完成确认 且 未达到最大提醒次数
            summaries = await async_get_many(
                QQMessageReceiptSummary,
                filters={
                    "next_reminder_at__lte": now,
                    "reminder_stage__lt": self.MAX_REMINDER_STAGE,
                },
            )
            
            # 进一步过滤：只处理未完成确认的消息
            pending_summaries = []
            for summary in summaries:
                if summary.confirmed_count < summary.expected_count:
                    pending_summaries.append(summary)
            
            if not pending_summaries:
                return
            
            logger.info(f"检查到 {len(pending_summaries)} 条需要提醒的消息")
            
            # 获取机器人实例
            try:
                bot = get_bot()
                if not bot:
                    logger.warning("无法获取机器人实例，跳过提醒")
                    return
            except Exception as e:
                logger.warning(f"获取机器人实例失败: {e}")
                return
            
            # 处理每条需要提醒的消息
            for summary in pending_summaries:
                try:
                    await self._send_reminder(bot, summary, now)
                except Exception as e:
                    logger.error(f"发送提醒失败 (message_id={summary.message_id}): {e}", exc_info=True)
        
        except Exception as e:
            logger.error(f"检查提醒时发生错误: {e}", exc_info=True)
    
    async def _send_reminder(
        self, bot: Bot, summary: QQMessageReceiptSummary, now: datetime
    ):
        """发送提醒消息"""
        # 获取消息记录
        from ...common.django_crud import async_get_one
        message = await async_get_one(QQRobotMessage, id=summary.message_id)
        if not message:
            logger.warning(f"未找到消息记录: message_id={summary.message_id}")
            return
        
        # 检查消息状态
        if message.status == QQRobotMessage.MessageStatus.CLOSED:
            logger.debug(f"消息已完成确认，跳过提醒: message_id={summary.message_id}")
            return
        
        if message.status == QQRobotMessage.MessageStatus.CANCELLED:
            logger.debug(f"消息已取消，跳过提醒: message_id={summary.message_id}")
            return
        
        # 检查是否是群消息
        if message.scene_type != "group" or not message.group_id:
            logger.debug(f"非群消息，跳过提醒: message_id={summary.message_id}")
            return
        
        group_id = int(message.group_id)
        outstanding = summary.outstanding_members or []
        
        if not outstanding:
            logger.debug(f"没有未确认成员，跳过提醒: message_id={summary.message_id}")
            return
        
        # 计算下次提醒时间
        current_stage = summary.reminder_stage
        if current_stage >= len(self.REMINDER_INTERVALS):
            logger.debug(f"已达到最大提醒次数，跳过提醒: message_id={summary.message_id}")
            return
        
        # 生成提醒消息
        reminder_msg = self._build_reminder_message(
            message, summary, outstanding, current_stage
        )
        
        # 发送提醒消息
        try:
            send_result = await bot.send_group_msg(group_id=group_id, message=reminder_msg)
            reminder_msg_id = send_result.get("message_id")
            reminder_msg_id_str = str(reminder_msg_id) if reminder_msg_id is not None else None
            
            logger.info(
                f"发送提醒成功: message_id={summary.message_id}, stage={current_stage + 1}, "
                f"outstanding_count={len(outstanding)}, reminder_msg_id={reminder_msg_id_str}"
            )
            
            # 保存提醒消息的msg_id到原始消息的metadata中，以便后续识别
            if reminder_msg_id_str:
                from ...common.django_crud import async_get_one, async_update_records
                current_metadata = message.metadata or {}
                reminder_msg_ids = current_metadata.get("reminder_msg_ids", [])
                if not isinstance(reminder_msg_ids, list):
                    reminder_msg_ids = []
                # 避免重复添加
                if reminder_msg_id_str not in reminder_msg_ids:
                    reminder_msg_ids.append(reminder_msg_id_str)
                    current_metadata["reminder_msg_ids"] = reminder_msg_ids
                    await async_update_records(
                        QQRobotMessage,
                        {"id": message.id},
                        {"metadata": current_metadata}
                    )
                    logger.debug(f"已保存提醒消息ID到metadata: message_id={message.id}, reminder_msg_id={reminder_msg_id_str}")
        except Exception as e:
            logger.error(f"发送提醒消息失败: {e}")
            raise
        
        # 更新提醒状态
        next_stage = current_stage + 1
        next_reminder_at = None
        
        if next_stage < self.MAX_REMINDER_STAGE:
            # 计算下次提醒时间
            interval_minutes = self.REMINDER_INTERVALS[next_stage]
            next_reminder_at = now + timedelta(minutes=interval_minutes)
        
        # 更新数据库
        from ...common.django_crud import async_update_records
        
        await async_update_records(
            QQMessageReceiptSummary,
            {"message_id": summary.message_id},
            {
                "reminder_stage": next_stage,
                "next_reminder_at": next_reminder_at,
            },
        )
    
    def _build_reminder_message(
        self,
        message: QQRobotMessage,
        summary: QQMessageReceiptSummary,
        outstanding: List[int],
        stage: int,
    ) -> str:
        """构建提醒消息"""
        outstanding_count = len(outstanding)
        total_count = summary.expected_count
        confirmed_count = summary.confirmed_count
        
        # 获取原始内容（去掉 [全员确认] 前缀）
        content = message.content
        if content.startswith("[全员确认]\n"):
            content = content[len("[全员确认]\n"):]
        if content.endswith("\n请通过任意表情确认收到。"):
            content = content[: -len("\n请通过任意表情确认收到。")]
        
        # 构建提醒消息
        lines = [
            f"[全员确认提醒 #{stage + 1}]",
            "",
            f"内容：{content}",
            "",
            f"确认进度：{confirmed_count}/{total_count}",
            f"还有 {outstanding_count} 位成员未确认，请尽快通过表情确认收到。",
        ]
        
        # @所有未确认成员
        try:
            # 构建@消息（使用 CQ 码格式）
            at_parts = []
            for uin in outstanding:
                at_parts.append(f"[CQ:at,qq={uin}]")
            
            if at_parts:
                at_msg = "".join(at_parts)
                lines.append("")
                lines.append(at_msg)
        except Exception as e:
            logger.debug(f"构建@消息失败: {e}")
        
        return "\n".join(lines)


# 全局调度器实例
_scheduler: Optional[AckReminderScheduler] = None


def get_scheduler() -> AckReminderScheduler:
    """获取调度器实例（单例模式）"""
    global _scheduler
    if _scheduler is None:
        _scheduler = AckReminderScheduler()
    return _scheduler


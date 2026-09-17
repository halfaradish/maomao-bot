"""
全员确认提醒调度器
负责定时检查未确认的消息并发送提醒

轮询由 APScheduler 的 interval job 驱动（见 ``register_job``），不再自建
``while + asyncio.sleep`` 循环：起停交给 ``nonebot_plugin_apscheduler``，
本模块只提供「一轮检查」的入口 ``tick()``。
"""
from __future__ import annotations

from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional

from nonebot import get_bot, get_driver, logger, require
from nonebot.adapters.onebot.v11 import Bot

from . import database
from .config import Config
from ...common.crud import async_get_many, async_get_one, async_update_records
from ...common.models.botdb_models import QQMessageReceiptSummary, QQRobotMessage

require("nonebot_plugin_apscheduler")
# 别名：本包 __init__.py 里 `scheduler` 这个名字已经绑给了 AckReminderScheduler 单例
from nonebot_plugin_apscheduler import scheduler as aps_scheduler  # noqa: E402

plugin_config = Config.parse_obj(get_driver().config.dict())

#: 检查任务的 job id（全局唯一，便于在日志/WebUI 里定位）
TICK_JOB_ID = "ack_manager_reminder_tick"
#: tick 迟到多少秒内仍然补跑。APScheduler 默认只给 1 秒，而一轮检查里有发消息的
#: 网络调用，必然超时——不显式放宽的话 tick 会被静默丢弃。
TICK_MISFIRE_GRACE = 30


class AckReminderScheduler:
    """全员确认提醒调度器"""
    
    # 提醒配置：每个阶段的提醒间隔（分钟）
    REMINDER_INTERVALS = [5, 15, 30]  # 5分钟后第一次提醒，15分钟后第二次，30分钟后第三次
    MAX_REMINDER_STAGE = len(REMINDER_INTERVALS)  # 最多提醒3次
    
    def __init__(self):
        self.check_interval = 60  # 检查间隔(秒)，每分钟检查一次

    async def tick(self):
        """执行一轮检查（apscheduler 的 job 目标）

        异常自己吞掉：job 抛异常不会终止后续调度，但会在 apscheduler 日志里刷
        traceback，且与旧的「出错继续下一轮」语义不符。
        """
        try:
            await self._check_and_send_reminders()
        except Exception as e:
            logger.error(f"全员确认提醒调度器错误: {e}", exc_info=True)
    
    async def _check_and_send_reminders(self):
        """检查并发送到期的提醒"""
        if not plugin_config.enabled:
            return
        try:
            now = datetime.now()
            
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
        if not plugin_config.enabled:
            return
        # 获取消息记录
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
                from ...common.crud import async_get_one, async_update_records
                current_metadata = message.metadata_ or {}
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


def register_job() -> None:
    """把「一轮检查」注册成 APScheduler 的 interval job

    插件禁用时不注册任何任务（等价于旧实现「禁用就不起循环」）。起停由
    ``nonebot_plugin_apscheduler`` 自己接管，这里不需要 on_startup/on_shutdown。
    """
    if not plugin_config.enabled:
        logger.info("ACK 插件已禁用，不注册提醒任务。")
        return

    interval = get_scheduler().check_interval
    aps_scheduler.add_job(
        get_scheduler().tick,
        "interval",
        seconds=interval,
        # 启动即跑一次，保持旧循环「起来就先查一遍」的语义
        next_run_time=datetime.now(aps_scheduler.timezone),
        id=TICK_JOB_ID,
        replace_existing=True,
        misfire_grace_time=TICK_MISFIRE_GRACE,
        coalesce=True,
        max_instances=1,
    )
    logger.info(f"全员确认提醒任务已注册: id={TICK_JOB_ID}, 每 {interval} 秒一次")


register_job()


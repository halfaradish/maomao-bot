from nonebot import (
    get_plugin_config,
    on_notice,
    logger,
    on_message
)
from nonebot.plugin import PluginMetadata
from nonebot.rule import Rule
from nonebot.adapters.onebot.v11.permission import GROUP
from nonebot.adapters.onebot.v11 import (
    GroupIncreaseNoticeEvent,
    GroupDecreaseNoticeEvent,
    Message,
    MessageSegment,
    GroupMessageEvent,
    Bot,
    ActionFailed
)

from datetime import datetime, timedelta
import asyncio
import threading
import time

from .config import Config
from ...common import JsonUtils, SendForwardMsg
from ..logging_info.message_dao import message_dao

__plugin_meta__ = PluginMetadata(
    name="auto_manage_group",
    description="",
    usage="",
    config=Config,
)

config = get_plugin_config(Config)

def is_group_increase(event) -> bool:
    return isinstance(event, GroupIncreaseNoticeEvent)
def is_group_decrease(event) -> bool:
    return isinstance(event, GroupDecreaseNoticeEvent)

group_increase = on_notice(rule=Rule(is_group_increase), priority=5, block=False)
group_decrease = on_notice(rule=Rule(is_group_decrease), priority=5, block=False)

def get_monitored_groups():
    data, _ = JsonUtils.read(
        filename=config.data_filename,
        default= {
            "monitored_groups": []
        }
    )
    return data.get('monitored_groups', [])

@group_increase.handle()
async def _(event: GroupIncreaseNoticeEvent):
    # 获取信息
    user_id: str = str(event.user_id)
    operator_id: str = str(event.operator_id)
    group_id: str = str(event.group_id)
    sub_type: str = event.sub_type

    monitored_groups = get_monitored_groups()
    if group_id not in monitored_groups:
        return
    
    increase_user: Message = Message([MessageSegment.at(user_id=user_id)])
    operator: Message = Message([MessageSegment.at(user_id=operator_id)])
    if sub_type == 'invite':
        await group_increase.finish("欢迎新成员 " + increase_user + f"({user_id}) 加入本群\n邀请人: " + operator + f"({operator_id})")
    else:
        await group_increase.finish("欢迎新成员 " + increase_user + f"({user_id}) 通过群号或二维码加入本群\n处理人: " + operator + f"({operator_id})")

@group_decrease.handle()
async def _(event: GroupDecreaseNoticeEvent):
    user_id: str = str(event.user_id)
    operator_id: str = str(event.operator_id)
    group_id: str = str(event.group_id)
    sub_type: str = event.sub_type

    monitored_groups = get_monitored_groups()
    if group_id not in monitored_groups:
        return
    
    decrease_user: Message = Message([MessageSegment.at(user_id=user_id)])
    operator: Message = Message([MessageSegment.at(user_id=operator_id)])
    if sub_type == 'leave':
        await group_decrease.finish(decrease_user + f"({user_id}) 主动离开了本群")
    elif sub_type == 'kick':
        await group_decrease.finish(decrease_user + f"({user_id}) 被踢出了本群\n处理人：" + operator + f"({operator_id})")


# 临时功能
def contains_banned_word(event: GroupMessageEvent):
    # 获取数据
    data, _ = JsonUtils.read(
        filename=config.data_filename,
        default={
            "ban_words": [],
            "ban_words_monitored_groups": []
        }
    )
    ban_words = data.get('ban_words', [])
    ban_words_monitored_groups = data.get('ban_words_monitored_groups', [])

    # 是否是违禁词检测群组
    group_id = event.group_id
    if str(group_id) not in ban_words_monitored_groups:
        return False
    # 是否包含违禁词
    message_txt = str(event.get_message())
    has_banned_word  = any(word in message_txt for word in ban_words)
    if not has_banned_word:
        return False
    # 发送者是否为管理员
    sender_role = event.sender.role
    if sender_role in ["admin", "owner"]:
        return False
    
    return True

banned_word_detector = on_message(
    rule=Rule(contains_banned_word),
    permission=GROUP,
    priority=20
)

async def context_erase_messages(bot: Bot, user_id: int, group_id: int, base_time: int, base_message_id: int):
    """上下文撤回消息"""
    try:
        # 等待延迟时间，确保logging_info插件完成消息存储
        await asyncio.sleep(config.context_erase_delay)
        
        # 计算时间范围
        start_time = base_time - config.context_erase_time_range
        end_time = base_time + config.context_erase_time_range
        
        logger.info(f"开始上下文撤回: 用户{user_id}, 群组{group_id}, 时间范围{start_time}-{end_time}")
        
        # 从数据库查询该用户在指定时间范围内的所有消息
        from django.db.models import Q
        from asgiref.sync import sync_to_async
        from botdb.models import MessageEventLog
        
        def _get_messages_sync():
            return list(
                MessageEventLog.objects.filter(
                    Q(user_id=user_id) & 
                    Q(group_id=group_id) & 
                    Q(time__gte=start_time) & 
                    Q(time__lte=end_time) &
                    ~Q(message_id=base_message_id)  # 排除基准消息（已撤回）
                ).order_by("time")
            )
        
        messages = await sync_to_async(_get_messages_sync)()
        
        # 调试日志：显示查询到的消息详情
        if messages:
            logger.info(f"查询到 {len(messages)} 条消息，时间范围: {start_time} - {end_time}")
            for i, msg in enumerate(messages[:5]):  # 只显示前5条消息的详情
                logger.info(f"消息{i+1}: ID={msg.message_id}, 时间={msg.time}, 内容长度={len(msg.raw_message)}")
        
        if not messages:
            logger.info(f"未找到需要撤回的上下文消息")
            return {"total": 0, "success": 0, "failed": 0, "messages": []}
            
        logger.info(f"找到 {len(messages)} 条需要撤回的上下文消息")
        
        # 批量撤回消息
        success_count = 0
        fail_count = 0
        
        # 创建异步撤回函数
        async def delete_message(msg):
            try:
                await bot.delete_msg(message_id=msg.message_id)
                return {"status": "success", "message_id": msg.message_id}
            except ActionFailed as e:
                return {"status": "failed", "message_id": msg.message_id, "error": e}
            except Exception as e:
                return {"status": "error", "message_id": msg.message_id, "error": e}
        
        # 创建任务列表
        tasks = []
        for msg in messages:
            tasks.append(delete_message(msg))
        
        # 并发执行所有撤回任务
        results = await asyncio.gather(*tasks, return_exceptions=True)
        
        # 统计结果
        for result in results:
            if isinstance(result, dict):
                if result["status"] == "success":
                    success_count += 1
                    logger.info(f"成功撤回消息: {result['message_id']}")
                else:
                    fail_count += 1
                    if result["status"] == "failed":
                        logger.warning(f"撤回消息失败: {result['message_id']}, 错误: {result.get('error', 'Unknown')}")
                    else:
                        logger.error(f"撤回消息异常: {result['message_id']}, 错误: {result.get('error', 'Unknown')}")
        
        logger.info(f"上下文撤回完成: 成功{success_count}条, 失败{fail_count}条")
        
        # 返回撤回统计信息和消息内容
        return {
            "total": len(messages),
            "success": success_count,
            "failed": fail_count,
            "messages": [{
                "message_id": msg.message_id,
                "time": msg.time,
                "content": msg.raw_message
            } for msg in messages]
        }
        
    except Exception as e:
        logger.error(f"上下文撤回过程异常: {e}")
        return {"total": 0, "success": 0, "failed": 0, "messages": []}


@banned_word_detector.handle()
async def _(bot: Bot, event: GroupMessageEvent):
    user_id = event.user_id
    group_id = event.group_id
    message_id = event.message_id
    current_time = event.time

    try:
        # 禁言用户
        await bot.set_group_ban(
            group_id=group_id,
            user_id=user_id,
            duration=3600
        )

        # 撤回当前消息
        await bot.delete_msg(message_id=message_id)

        user_segment = MessageSegment.at(user_id=user_id)
        await banned_word_detector.send(f"检测到消息包含违规词，已对 " + user_segment + f"({user_id})禁言 1 小时")

        # 启动上下文撤回任务并获取结果
        erase_result = await context_erase_messages(bot, user_id, group_id, current_time, message_id)

        # 构建日志消息
        remind_msgs = []
        remind_msgs.append(f"在群组：{group_id} 检测到违禁消息")
        remind_msgs.append(f"违禁用户：{user_id}")
        remind_msgs.append(f"{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        remind_msgs.append("违禁消息如下")
        remind_msgs.append(str(event.get_message()))
        
        # 添加上下文撤回统计信息
        if erase_result:
            total_messages = erase_result["total"]
            success_count = erase_result["success"]
            failed_count = erase_result["failed"]
            
            remind_msgs.append(f"上下文撤回统计：共{total_messages}条消息，成功撤回{success_count}条，失败{failed_count}条")
            
            # 展示被撤回的消息内容
            if erase_result["messages"]:
                remind_msgs.append("被撤回的消息内容：")
                for i, msg_info in enumerate(erase_result["messages"], 1):
                    msg_time = datetime.fromtimestamp(msg_info["time"]).strftime('%Y-%m-%d %H:%M:%S')
                    remind_msgs.append(f"{i}. [{msg_time}] {msg_info['content']}")
        else:
            remind_msgs.append("上下文撤回机制已启动")

        data, _ = JsonUtils.read(
            filename=config.data_filename,
            default={"ban_words_remind_groups": []}
        )
        # 发送消息
        ban_words_remind_groups = data.get('ban_words_remind_groups', [])
        for remind_group in ban_words_remind_groups:
            await SendForwardMsg.by_onebot_api(bot=bot, event=event, messges=remind_msgs, group_id=remind_group)

    except ActionFailed as e:
        print(f"操作失败: {e}")
    except Exception as e:
        print(f"未知错误: {e}")
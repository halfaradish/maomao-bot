"""
消息发送限速中间件
在bot连接时hook send方法，添加限速逻辑
"""
from typing import TYPE_CHECKING, Any, Optional
from collections import defaultdict
import time
from nonebot import get_driver, get_plugin_config, logger
from nonebot.adapters.onebot.v11 import Bot, GroupMessageEvent
from ...common.rate_limiter import GroupRateLimiter
from .config import Config

if TYPE_CHECKING:
    from nonebot.adapters.onebot.v11 import Message, MessageSegment

# 尝试从配置文件读取配置，失败则使用默认配置
try:
    plugin_config = get_plugin_config(Config)
    RATE_LIMIT_CONFIG = {
        "enabled": plugin_config.enabled,
        "capacity": plugin_config.capacity,
        "refill_rate": plugin_config.refill_rate,
        "per_group": plugin_config.per_group,
        "emergency_stop": plugin_config.emergency_stop,
        "auto_stop_threshold": plugin_config.auto_stop_threshold,
        "auto_stop_time_window": plugin_config.auto_stop_time_window,
    }
except Exception:
    # 如果配置文件读取失败，使用默认配置
    RATE_LIMIT_CONFIG = {
        "enabled": True,  # 是否启用限速
        "capacity": 5,    # 桶容量（允许突发5条）
        "refill_rate": 2.0,  # 补充速率（每秒2条）
        "per_group": False,  # True=按群限速，False=全局限速
        "emergency_stop": False,  # 紧急停止开关
        "auto_stop_threshold": 20,  # 单个群连续发送超过此数量时自动紧急停止
        "auto_stop_time_window": 60,  # 时间窗口（秒），在此时间内连续发送才会触发自动停止
    }

# 创建限速器实例
limiter = GroupRateLimiter(
    capacity=RATE_LIMIT_CONFIG["capacity"],
    refill_rate=RATE_LIMIT_CONFIG["refill_rate"]
)

# 跟踪每个群的消息计数和时间
group_message_tracker: dict[int, dict] = defaultdict(lambda: {"count": 0, "first_msg_time": None})


def check_if_would_exceed_threshold(group_id: Optional[int]) -> bool:
    """
    检查如果发送这条消息，是否会超过阈值
    这是一个预计数检查，在实际发送前进行，避免已经通过检查的请求继续执行
    
    Args:
        group_id: 群组ID
        
    Returns:
        True: 如果发送后会超过阈值
        False: 如果发送后不会超过阈值
    """
    if group_id is None:
        return False  # 不是群消息，不检查
    
    now = time.time()
    tracker = group_message_tracker[group_id]
    
    # 检查时间窗口
    if tracker["first_msg_time"] is None:
        # 第一次发送消息，发送后计数为1，不会超过阈值（假设阈值>=1）
        return False
    else:
        elapsed = now - tracker["first_msg_time"]
        if elapsed > RATE_LIMIT_CONFIG["auto_stop_time_window"]:
            # 超出时间窗口，发送后计数为1，不会超过阈值
            return False
        else:
            # 在时间窗口内，预计计数为当前计数+1
            predicted_count = tracker["count"] + 1
            # 如果预计计数 > 阈值，则会超过阈值
            # 例如：阈值20，当前计数19，预计20，允许发送（最多20条）
            #       阈值20，当前计数20，预计21，拒绝发送（已到上限）
            return predicted_count > RATE_LIMIT_CONFIG["auto_stop_threshold"]


async def check_and_update_group_message_count(group_id: Optional[int], bot: Bot, event: Optional[GroupMessageEvent] = None):
    """
    检查并更新群消息计数，如果超过阈值则自动触发紧急停止
    
    Args:
        group_id: 群组ID
        bot: Bot实例（用于发送通知消息）
        event: 事件实例（用于发送通知消息，可选）
    """
    if group_id is None:
        return  # 不是群消息，不处理
    
    now = time.time()
    tracker = group_message_tracker[group_id]
    
    # 检查时间窗口，如果超出窗口则重置计数
    if tracker["first_msg_time"] is None:
        # 第一次发送消息，初始化
        tracker["first_msg_time"] = now
        tracker["count"] = 1
    else:
        elapsed = now - tracker["first_msg_time"]
        if elapsed > RATE_LIMIT_CONFIG["auto_stop_time_window"]:
            # 超出时间窗口，重置计数
            tracker["first_msg_time"] = now
            tracker["count"] = 1
        else:
            # 在时间窗口内，增加计数
            tracker["count"] += 1
    
    logger.debug(f"[限速器] 群 {group_id} 连续消息计数: {tracker['count']}/{RATE_LIMIT_CONFIG['auto_stop_threshold']}")
    
    # 检查是否超过阈值
    if tracker["count"] >= RATE_LIMIT_CONFIG["auto_stop_threshold"]:
        logger.warning(f"[限速器] ⚠️ 群 {group_id} 在 {RATE_LIMIT_CONFIG['auto_stop_time_window']} 秒内发送了 {tracker['count']} 条消息，超过阈值 {RATE_LIMIT_CONFIG['auto_stop_threshold']}，自动触发紧急停止！")
        
        # 自动触发紧急停止
        RATE_LIMIT_CONFIG["emergency_stop"] = True
        
        # 尝试发送通知消息
        try:
            original_send = getattr(bot, '_original_send', None)
            notification_msg = f"🛑 自动紧急停止已触发！\n检测到群内 {RATE_LIMIT_CONFIG['auto_stop_time_window']} 秒内连续发送了 {tracker['count']} 条消息（阈值: {RATE_LIMIT_CONFIG['auto_stop_threshold']} 条）。\n使用「限速恢复」命令可以恢复。"
            
            # 优先使用event发送（通过bot.send）
            if original_send and event:
                await original_send(event=event, message=notification_msg)
            # 如果没有event，尝试使用call_api直接发送群消息
            elif getattr(bot, '_original_call_api', None):
                await bot._original_call_api('send_group_msg', group_id=group_id, message=notification_msg)
        except Exception as e:
            logger.error(f"[限速器] ⚠️ 无法发送自动紧急停止通知: {e}")


def reset_group_message_count(group_id: Optional[int]):
    """重置群消息计数"""
    if group_id is not None:
        group_message_tracker[group_id] = {"count": 0, "first_msg_time": None}
        logger.info(f"[限速器] 群 {group_id} 的消息计数已重置")


def setup_rate_limiter_for_bot(bot: Bot):
    """
    Bot连接时的钩子函数
    替换bot.send方法，添加限速逻辑
    """
    logger.info("[限速器] 正在初始化消息发送限速中间件...")

    # 保存原始的send方法（存储到bot实例上，方便后续访问）
    original_send = bot.send
    bot._original_send = original_send  # 保存到bot实例上

    async def rate_limited_send(*args, **kwargs):
        """
        带限速的消息发送方法

        这个方法会拦截所有 bot.send() 调用
        使用 *args, **kwargs 来兼容不同的调用方式
        
        注意：限速和计数都在 call_api 中统一处理，因为 send 内部会调用 call_api
        这样可以避免重复限速和计数
        """
        logger.debug(f"[限速器] 🔍 拦截到 bot.send 调用")
        
        # 只检查紧急停止（限速和计数都在 call_api 中统一处理）
        if RATE_LIMIT_CONFIG["emergency_stop"]:
            logger.warning("[限速器] ⚠️ 紧急停止已启用，消息发送被阻止")
            raise RuntimeError("紧急停止：消息发送已被阻止")

        # 直接调用原始send方法（限速和计数会在 call_api 中处理）
        result = await original_send(*args, **kwargs)
        logger.debug(f"[限速器] ✅ bot.send 调用完成")
        
        return result

    # 同时hook call_api方法（NoneBot可能通过call_api发送消息）
    original_call_api = bot.call_api
    bot._original_call_api = original_call_api
    
    async def rate_limited_call_api(api: str, **data):
        """
        带限速的API调用方法
        拦截send_msg相关的API调用（包括转发消息）
        """
        # 只对消息发送相关的API进行限速（包括转发消息）
        message_apis = [
            'send_msg', 
            'send_private_msg', 
            'send_group_msg',
            'send_group_forward_msg',
            'send_private_forward_msg'
        ]
        
        if api in message_apis:
            logger.debug(f"[限速器] 🔍 拦截到 call_api: {api}")
            
            # 检查是否启用限速
            if not RATE_LIMIT_CONFIG["enabled"]:
                return await original_call_api(api, **data)

            # 检查紧急停止
            if RATE_LIMIT_CONFIG["emergency_stop"]:
                logger.warning("[限速器] ⚠️ 紧急停止已启用，API调用被阻止")
                raise RuntimeError("紧急停止：消息发送已被阻止")

            # 提取群组ID
            # send_group_msg 和 send_group_forward_msg 直接有 group_id
            # send_msg 需要通过 message_type 判断
            # send_private_msg 和 send_private_forward_msg 是私聊，没有 group_id
            group_id = None
            if api == 'send_group_msg' or api == 'send_group_forward_msg':
                group_id = data.get('group_id')
            elif api == 'send_msg':
                # send_msg API可能需要根据message_type判断
                if data.get('message_type') == 'group' and 'group_id' in data:
                    group_id = data['group_id']
            
            # 确保 group_id 是 int 类型（API 可能返回字符串）
            if group_id is not None:
                try:
                    group_id = int(group_id)
                except (TypeError, ValueError):
                    logger.warning(f"[限速器] 无法转换 group_id 为 int: {group_id}")
                    group_id = None
            
            if group_id:
                logger.debug(f"[限速器] 检测到群消息，群号: {group_id}")
            elif api in ['send_group_msg', 'send_group_forward_msg']:
                logger.debug(f"[限速器] 检测到转发消息（群）或群消息，但未找到有效的 group_id")

            # 🔴 关键改进：在获取令牌之前先进行预计数检查
            # 这样可以避免已经通过检查的请求在队列中等待，导致超过阈值
            if group_id is not None:
                if check_if_would_exceed_threshold(group_id):
                    # 如果发送后会超过阈值，立即触发紧急停止并拒绝请求
                    logger.warning(f"[限速器] ⚠️ 预计发送后会超过阈值，立即触发紧急停止并拒绝请求（群号: {group_id}）")
                    
                    # 先触发紧急停止（防止其他请求继续）
                    RATE_LIMIT_CONFIG["emergency_stop"] = True
                    
                    # 发送通知消息（需要绕过限速器）
                    try:
                        tracker = group_message_tracker[group_id]
                        notification_msg = f"🛑 自动紧急停止已触发！\n检测到即将超过阈值，已阻止消息发送（当前计数: {tracker['count']}/{RATE_LIMIT_CONFIG['auto_stop_threshold']} 条）。\n使用「限速恢复」命令可以恢复。"
                        if getattr(bot, '_original_call_api', None):
                            await bot._original_call_api('send_group_msg', group_id=group_id, message=notification_msg)
                    except Exception as e:
                        logger.error(f"[限速器] ⚠️ 无法发送自动紧急停止通知: {e}")
                    
                    # 拒绝这个请求
                    raise RuntimeError(f"紧急停止：消息发送已被阻止（预计发送后会超过阈值 {RATE_LIMIT_CONFIG['auto_stop_threshold']} 条）")

            # 获取令牌
            logger.debug(f"[限速器] ⏳ 等待令牌... (模式: {'按群' if RATE_LIMIT_CONFIG['per_group'] else '全局'})")
            try:
                if RATE_LIMIT_CONFIG["per_group"]:
                    await limiter.acquire(group_id)
                else:
                    await limiter.acquire(None)
                logger.debug(f"[限速器] ✅ 获得令牌，准备调用API")
            except Exception as e:
                logger.error(f"[限速器] ❌ 获取令牌时出错: {e}")
                raise

            # 🔴 双重检查：在获取令牌后再次检查（处理并发情况）
            # 因为在等待令牌的过程中，可能已经有其他消息发送了
            if group_id is not None:
                # 再次检查紧急停止状态（可能在等待令牌期间被其他请求触发）
                if RATE_LIMIT_CONFIG["emergency_stop"]:
                    logger.warning(f"[限速器] ⚠️ 在等待令牌期间，紧急停止已触发，拒绝发送（群号: {group_id}）")
                    raise RuntimeError("紧急停止：消息发送已被阻止")
                
                # 再次检查预计数（可能在等待令牌期间，其他请求已经发送了消息）
                if check_if_would_exceed_threshold(group_id):
                    logger.warning(f"[限速器] ⚠️ 在等待令牌期间，预计数已超过阈值，拒绝发送（群号: {group_id}）")
                    # 触发紧急停止
                    RATE_LIMIT_CONFIG["emergency_stop"] = True
                    raise RuntimeError(f"紧急停止：消息发送已被阻止（预计发送后会超过阈值 {RATE_LIMIT_CONFIG['auto_stop_threshold']} 条）")

            result = await original_call_api(api, **data)
            logger.debug(f"[限速器] ✅ API调用完成")
            
            # 只在 call_api 中计数（这是真正发送消息的地方）
            # 这样可以避免 bot.send() 和 call_api() 重复计数的问题
            if group_id is not None:
                # 注意：call_api中没有event，所以传None，函数会使用call_api发送通知
                await check_and_update_group_message_count(group_id, bot, None)
            
            return result
        else:
            # 非消息发送API，直接调用
            return await original_call_api(api, **data)

    # 替换bot的方法
    bot.send = rate_limited_send
    bot.call_api = rate_limited_call_api

    logger.info(f"[限速器] ✅ 限速中间件已启用")
    logger.info(f"  - 桶容量: {RATE_LIMIT_CONFIG['capacity']} 条")
    logger.info(f"  - 限速速率: {RATE_LIMIT_CONFIG['refill_rate']} 条/秒")
    logger.info(f"  - 限速模式: {'按群限速' if RATE_LIMIT_CONFIG['per_group'] else '全局限速'}")


# 注册bot连接事件监听器
driver = get_driver()


@driver.on_bot_connect
async def on_bot_connect(bot: Bot):
    """Bot连接时自动调用"""
    setup_rate_limiter_for_bot(bot)


# 控制命令
from nonebot import on_command

logger.info("[限速器] 正在注册控制命令...")

enable_rate_limit_cmd = on_command("限速启用", priority=1)
disable_rate_limit_cmd = on_command("限速禁用", priority=1)
emergency_stop_cmd = on_command("限速紧急停止", priority=1)
resume_rate_limit_cmd = on_command("限速恢复", priority=1)  # 恢复限速（取消紧急停止）
rate_limit_status_cmd = on_command("限速状态", priority=1)
switch_global_mode_cmd = on_command("限速全局", priority=1)
switch_group_mode_cmd = on_command("限速按群", priority=1)
rate_help_cmd = on_command("rate", priority=1)  # 显示所有限速相关命令

logger.info("[限速器] ✅ 控制命令已注册: 限速启用, 限速禁用, 限速紧急停止, 限速恢复, 限速状态, 限速全局, 限速按群, rate")


@enable_rate_limit_cmd.handle()
async def enable_rate_limit(bot: Bot, event: GroupMessageEvent):
    """启用限速"""
    RATE_LIMIT_CONFIG["enabled"] = True
    RATE_LIMIT_CONFIG["emergency_stop"] = False
    await enable_rate_limit_cmd.finish("✅ 限速器已启用")


@disable_rate_limit_cmd.handle()
async def disable_rate_limit(bot: Bot, event: GroupMessageEvent):
    """禁用限速"""
    RATE_LIMIT_CONFIG["enabled"] = False
    await disable_rate_limit_cmd.finish("✅ 限速器已禁用")


@emergency_stop_cmd.handle()
async def emergency_stop_handler(bot: Bot, event: GroupMessageEvent):
    """紧急停止所有消息发送"""
    # 先发送确认消息（在设置紧急停止之前）
    try:
        # 使用保存的原始send方法绕过限速器检查
        original_send = getattr(bot, '_original_send', None)
        if original_send:
            await original_send(event=event, message="🛑 紧急停止已启用！\n所有后续消息发送将被阻止。\n使用「限速恢复」命令可以恢复。")
        else:
            # 如果找不到原始方法，直接使用bot.send（在紧急停止设置前）
            await bot.send(event=event, message="🛑 紧急停止已启用！\n所有后续消息发送将被阻止。\n使用「限速恢复」命令可以恢复。")
    except Exception as e:
        # 如果发送失败，至少打印日志
        logger.error(f"[限速器] ⚠️ 无法发送紧急停止确认消息: {e}")
    
    # 设置紧急停止（在所有确认消息发送后再设置）
    RATE_LIMIT_CONFIG["emergency_stop"] = True
    RATE_LIMIT_CONFIG["enabled"] = True  # 保持限速器启用状态
    
    # 不再调用finish，因为已经手动发送了消息
    logger.warning(f"[限速器] ⚠️ 紧急停止已启用（群号: {event.group_id}）")


@resume_rate_limit_cmd.handle()
async def resume_rate_limit(bot: Bot, event: GroupMessageEvent):
    """恢复限速（取消紧急停止）"""
    # 先取消紧急停止
    RATE_LIMIT_CONFIG["emergency_stop"] = False
    RATE_LIMIT_CONFIG["enabled"] = True
    
    # 重置当前群的消息计数
    reset_group_message_count(event.group_id)
    
    # 发送恢复消息（现在可以正常发送了）
    try:
        original_send = getattr(bot, '_original_send', None)
        if original_send:
            await original_send(event=event, message="✅ 限速器已恢复！\n紧急停止已取消，消息计数已重置，消息发送恢复正常。")
        else:
            await bot.send(event=event, message="✅ 限速器已恢复！\n紧急停止已取消，消息计数已重置，消息发送恢复正常。")
    except Exception as e:
        logger.error(f"[限速器] ⚠️ 无法发送恢复确认消息: {e}")
    
    logger.info(f"[限速器] ✅ 紧急停止已取消，限速器恢复正常（群号: {event.group_id}）")


@rate_limit_status_cmd.handle()
async def rate_limit_status(bot: Bot, event: GroupMessageEvent):
    """查看限速状态"""
    logger.debug(f"[限速器] 收到限速状态查询命令，群号: {event.group_id}")
    status = "启用" if RATE_LIMIT_CONFIG["enabled"] else "禁用"
    stop = "是" if RATE_LIMIT_CONFIG["emergency_stop"] else "否"
    mode = "按群限速" if RATE_LIMIT_CONFIG["per_group"] else "全局限速"

    # 显示当前群的计数信息
    current_count = group_message_tracker.get(event.group_id, {}).get("count", 0)
    
    msg = f"""📊 限速器状态
状态: {status}
紧急停止: {stop}
限速模式: {mode}
桶容量: {RATE_LIMIT_CONFIG['capacity']} 条
限速速率: {RATE_LIMIT_CONFIG['refill_rate']} 条/秒
自动停止阈值: {RATE_LIMIT_CONFIG['auto_stop_threshold']} 条/{RATE_LIMIT_CONFIG['auto_stop_time_window']} 秒
当前群计数: {current_count}/{RATE_LIMIT_CONFIG['auto_stop_threshold']}"""

    await rate_limit_status_cmd.finish(msg)


@switch_global_mode_cmd.handle()
async def switch_global_mode(bot: Bot, event: GroupMessageEvent):
    """切换到全局限速模式"""
    RATE_LIMIT_CONFIG["per_group"] = False
    await switch_global_mode_cmd.finish("✅ 已切换到全局限速模式\n所有群共享同一个限速桶")


@switch_group_mode_cmd.handle()
async def switch_group_mode(bot: Bot, event: GroupMessageEvent):
    """切换到按群限速模式"""
    RATE_LIMIT_CONFIG["per_group"] = True
    await switch_group_mode_cmd.finish("✅ 已切换到按群限速模式\n每个群使用独立的限速桶")


@rate_help_cmd.handle()
async def rate_help(bot: Bot, event: GroupMessageEvent):
    """显示所有限速相关命令"""
    help_msg = """📋 限速器命令列表

🔹 限速启用 - 启用消息发送限速功能
🔹 限速禁用 - 禁用消息发送限速功能
🔹 限速紧急停止 - 立即停止所有消息发送（用于紧急情况）
🔹 限速恢复 - 取消紧急停止，恢复正常消息发送
🔹 限速状态 - 查看当前限速器状态和配置
🔹 限速全局 - 切换到全局限速模式（所有群共享限速）
🔹 限速按群 - 切换到按群限速模式（每个群独立限速）
🔹 rate - 显示此帮助信息

💡 提示：限速器用于防止机器人发送消息过快被风控
💡 所有命令都以「限速」或「rate」开头，避免误触"""
    
    await rate_help_cmd.finish(help_msg)


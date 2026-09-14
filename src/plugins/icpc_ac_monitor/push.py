# src/plugins/icpc_ac_monitor/push.py
"""bot 实例/事件循环缓存与 AC 推送

_main_event_loop 是本模块级全局变量：监控线程与启动恢复钩子
必须通过 push._main_event_loop 属性读写（跨模块直接 from-import
会在导入时复制 None 值，导致线程拿不到循环）。
"""

import asyncio
from typing import Optional, Union

from nonebot import get_bot, logger
from nonebot.adapters.onebot.v11 import Bot, Message, MessageSegment

from .state import AT_WHITELIST

# 全局变量：存储 bot 实例和主事件循环（在启动时设置）
_cached_bot: Optional[Bot] = None
_main_event_loop: Optional[asyncio.AbstractEventLoop] = None

def _get_main_loop():
    """获取主事件循环"""
    try:
        return asyncio.get_running_loop()
    except RuntimeError:
        try:
            loop = asyncio.get_event_loop()
            return loop if loop.is_running() else None
        except Exception:
            return None

def set_bot_instance(bot: Bot):
    """在启动时设置 bot 实例和主事件循环"""
    global _cached_bot, _main_event_loop
    _cached_bot = bot
    _main_event_loop = _get_main_loop()

def _build_push_message(content: str, group_id: Optional[int]) -> Message:
    """根据目标群构建带 @ 的消息"""
    mentions = []
    for qq, bind_group in AT_WHITELIST.items():
        if bind_group is None or (group_id is not None and bind_group == group_id):
            mentions.append(str(qq))
    if not mentions:
        return Message(content)
    msg = Message()
    for qq in mentions:
        msg += MessageSegment.at(qq)
        msg += MessageSegment.text(" ")
    msg += MessageSegment.text("\n" + content)
    return msg


async def send_ac_msg(group_id: int, message: Union[str, Message]):
    """
    利用缓存的 bot 实例或 get_bot() 异步向指定群发消息。
    失败时只记日志，不中断线程。
    """
    try:
        # 优先使用缓存的 bot 实例
        bot = _cached_bot
        if bot is None:
            # 如果缓存中没有，尝试获取
            try:
                bot = get_bot()
            except Exception as e:
                logger.error(f"无法获取 bot 实例：{e}")
                raise

        result = await bot.send_group_msg(group_id=group_id, message=message)
        return result
    except Exception as e:
        logger.error(f"推送失败（群{group_id}）：{e}")
        raise

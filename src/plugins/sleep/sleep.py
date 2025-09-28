import asyncio
import random
from nonebot import get_driver, get_plugin_config, logger
from nonebot.adapters import Event
from nonebot.plugin import PluginMetadata
from nonebot.adapters.onebot.v11 import MessageEvent
from nonebot.message import event_preprocessor

from .config import Config

plugin_config = get_plugin_config(Config)

__plugin_meta__ = PluginMetadata(
    name="sleep",
    description="",
    usage="",
    config=Config,
)

driver = get_driver()
delay_enabled = driver.config.delay_enabled if hasattr(driver.config, "delay_enabled") else False

@event_preprocessor
async def global_random_delay(event: Event):
    if not delay_enabled:
        return
    
    # 仅处理MessageEvent事件
    if not isinstance(event, MessageEvent):
        return
    
    min_time = plugin_config.min_sleep_time
    max_time = plugin_config.max_sleep_time
    
    delay = random.uniform(min_time, max_time)
    logger.info(f"随机延迟{delay:.2f}秒回复")
    await asyncio.sleep(delay)
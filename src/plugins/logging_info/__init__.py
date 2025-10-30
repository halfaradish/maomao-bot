from nonebot import (
    get_plugin_config,
    on_message,
    logger
)
from nonebot.adapters.onebot.v11 import (
    PrivateMessageEvent,
    GroupMessageEvent,
)
from nonebot.rule import Rule
from nonebot.plugin import PluginMetadata
from typing import Union

from .message_dao import message_dao
from .config import Config

__plugin_meta__ = PluginMetadata(
    name="logging_info",
    description="",
    usage="",
    config=Config,
)

config = get_plugin_config(Config)

def is_message_event(event):
    return isinstance(event, (PrivateMessageEvent, GroupMessageEvent))

message_listen = on_message(
    priority=config.logging_info_priority,
    block=config.logging_info_block,
    rule=Rule(is_message_event)
)

@message_listen.handle()
async def listen(event: Union[PrivateMessageEvent, GroupMessageEvent]):
    """存储消息"""
    event_dict = event.dict()

    success = message_dao.save_message(event_data=event_dict)

    if success:
        logger.info(f"已保存消息：{event.message_id}")
    else:
        logger.error(f"保存失败：{event.message_id}")
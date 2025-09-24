from nonebot import (
    get_plugin_config,
    on_notice
)
from nonebot.plugin import PluginMetadata
from nonebot.adapters.onebot.v11 import (
    GroupIncreaseNoticeEvent,
    Message,
    MessageSegment
)

from .config import Config
from ...common import JsonUtils

__plugin_meta__ = PluginMetadata(
    name="auto_manage_group",
    description="",
    usage="",
    config=Config,
)

config = get_plugin_config(Config)

group_increase = on_notice()

@group_increase.handle()
async def _(event: GroupIncreaseNoticeEvent):
    user_id: str = str(event.user_id)
    operator_id: str = str(event.operator_id)
    group_id: str = str(event.group_id)

    data, _ = JsonUtils.read(
        filename=config.data_filename,
        default= {
            "monitored_groups": []
        }
    )

    monitored_groups = data.get('monitored_groups')
    if group_id not in monitored_groups:
        return
    
    increase_user: Message = Message([MessageSegment.at(user_id=user_id)])
    operator: Message = Message([MessageSegment.at(user_id=operator_id)])
    await group_increase.finish("欢迎新成员" + increase_user + f"({user_id}加入本群\n处理人: " + operator + f"({operator_id})")


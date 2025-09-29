from nonebot import (
    get_plugin_config,
    on_notice,
    logger
)
from nonebot.plugin import PluginMetadata
from nonebot.adapters.onebot.v11 import (
    GroupIncreaseNoticeEvent,
    GroupDecreaseNoticeEvent,
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
group_decrease = on_notice()

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

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

from datetime import datetime

from .config import Config
from ...common import JsonUtils, SendForwardMsg

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

@banned_word_detector.handle()
async def _(bot: Bot, event: GroupMessageEvent):
    user_id = event.user_id
    group_id = event.group_id
    message_id = event.message_id

    try:
        # 禁言用户
        await bot.set_group_ban(
            group_id=group_id,
            user_id=user_id,
            duration=3600
        )

        # 撤回消息
        await bot.delete_msg(message_id=message_id)

        user_segment = MessageSegment.at(user_id=user_id)
        await banned_word_detector.send(f"检测到消息包含违规词，已对 " + user_segment + f"({user_id})禁言 1 小时")

        # 构建日志消息
        remind_msgs = []
        remind_msgs.append(f"在群组：{group_id} 检测到违禁消息")
        remind_msgs.append(f"违禁用户：{user_id}")
        remind_msgs.append(f"{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        remind_msgs.append("违禁消息如下")
        remind_msgs.append(str(event.get_message()))

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
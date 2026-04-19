from nonebot import logger, on_command
from nonebot.plugin import PluginMetadata
from nonebot.adapters.onebot.v11 import GroupMessageEvent, Bot
from nonebot.exception import FinishedException, ActionFailed

from ...common.json_utils import JsonUtils
from src.common.model.model import PluginGroupEnum, PluginBadgeColor

__plugin_meta__ = PluginMetadata(
    name="群消息撤回",
    description="支持在群聊中撤回消息，根据机器人角色权限执行不同的撤回操作",
    usage="撤回 + 回复目标消息 —— 撤回指定消息\ndelete + 回复目标消息 —— 撤回指定消息",
    supported_adapters={"~onebot.v11"},
    extra={
        "group": PluginGroupEnum.GROUP_MANAGE.value,
        "badge_color": PluginBadgeColor.BLUE.value
    },
)


delete_msg = on_command(
    "撤回",
    aliases={'delete'},
    priority=30,
    block=False
)

PLUGIN_DATA = 'group_msg_del.json'

def _read_plugin_data():
    return JsonUtils.read(
        filename=PLUGIN_DATA,
        default={
            "user_whitelist": []
        }
    )
    

@delete_msg.handle()
async def _(bot: Bot, event: GroupMessageEvent):
    if not event or not event.reply:
        return
    
    json_data = _read_plugin_data()
    user_whitelist = json_data.get('user_whitelist', [])

    current_user_id = str(event.sender.user_id)
    whitelist_str = [str(uid) for uid in user_whitelist]
    
    if current_user_id not in whitelist_str:
        # 非白名单用户直接忽略，不暴露机器人功能
        return
    
    target_msg_id  = event.reply.message_id
    target_user_id = event.reply.sender.user_id
    group_id = event.group_id
    bot_user_id = int(bot.self_id)

    try:
        bot_info = await bot.get_group_member_info(
            group_id=group_id,
            user_id=bot_user_id
        )
        target_info = await bot.get_group_member_info(
            group_id=group_id,
            user_id=target_user_id
        )

        if not bot_info or not target_info:
            logger.info("获取群成员信息失败，请重试。")
            return
        
        bot_role = bot_info['role'] # 'owner', 'admin', or 'member'
        target_role = target_info['role']

        can_recall = False

        # 情况 1: Bot 是群主 -> 撤回任何人
        if bot_role == 'owner':
            can_recall = True

        # 情况 2: Bot 是管理员 -> 撤回除群主以外的人
        elif bot_role == 'admin':
            if target_role != 'owner':
                can_recall = True
            else:
                await delete_msg.finish("管理员无权撤回群主的消息。")

        # 情况 3: Bot 是普通成员 -> 只能撤回自己
        else:
            if target_user_id == bot_user_id:
                can_recall = True
            else:
                await delete_msg.finish("普通成员只能撤回自己的消息。")

        if can_recall:
            await bot.delete_msg(message_id=target_msg_id)
            await delete_msg.finish("消息已撤回")

    except FinishedException:
        return
    except ActionFailed as e:
        # 处理 API 调用失败的情况 (如消息超过2分钟)
        await delete_msg.finish(f"撤回操作失败: {e}")
    except Exception as e:
        # 处理其他未知错误
        await delete_msg.finish(f"发生错误: {e}")
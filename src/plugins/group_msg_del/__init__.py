from nonebot import logger, on_command
from nonebot.plugin import PluginMetadata
from nonebot.adapters.onebot.v11 import GroupMessageEvent, Bot
from nonebot.exception import FinishedException, ActionFailed

from src.common.permission import check_permission
from src.common.model.model import PluginGroupEnum, PluginBadgeColor
from . import permissions  # noqa: F401 - 注册权限点到权限系统

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


@delete_msg.handle()
async def _(bot: Bot, event: GroupMessageEvent):
    if not event.reply:
        return

    if not await check_permission(event, "group_msg_del:use"):
        logger.info(f"[群消息撤回] 用户 {event.user_id} 无权限，忽略操作")
        return
    
    target_msg_id  = event.reply.message_id
    target_user_id = event.reply.sender.user_id
    group_id = event.group_id
    bot_user_id = int(bot.self_id)

    logger.info(f"[群消息撤回] 目标消息ID: {target_msg_id}, 目标用户: {target_user_id}, 群: {group_id}")

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
        
        logger.info(f"[群消息撤回] 机器人角色: {bot_role}, 目标用户角色: {target_role}")

        can_recall = False

        # 情况 1: Bot 是群主 -> 撤回任何人
        if bot_role == 'owner':
            can_recall = True
            logger.info("[群消息撤回] 机器人是群主，允许撤回")

        # 情况 2: Bot 是管理员 -> 撤回除群主/管理员以外的人
        elif bot_role == 'admin':
            if target_user_id == bot_user_id:
                can_recall = True
                logger.info("[群消息撤回] 机器人是管理员，可以调用群撤回撤回自己的消息")
            elif target_role != 'owner' and target_role != 'admin':
                can_recall = True
                logger.info("[群消息撤回] 机器人是管理员，目标用户不是群主或管理员，允许撤回")
            else:
                logger.info("[群消息撤回] 管理员无权撤回群主或其他管理员的消息")
                await delete_msg.finish("管理员无权撤回群主或其他管理员的消息。")

        # 情况 3: Bot 是普通成员 -> 只能撤回自己
        else:
            if target_user_id == bot_user_id:
                can_recall = True
                logger.info("[群消息撤回] 机器人是普通成员，只能撤回自己的消息")
            else:
                logger.info("[群消息撤回] 普通成员只能撤回自己的消息")
                await delete_msg.finish("普通成员只能撤回自己的消息。")

        if can_recall:
            logger.info(f"[群消息撤回] 执行撤回操作，消息ID: {target_msg_id}")
            await bot.delete_msg(message_id=target_msg_id)
            logger.info(f"[群消息撤回] 撤回成功，消息ID: {target_msg_id}")
            await delete_msg.finish("消息已撤回")

    except FinishedException:
        return
    except ActionFailed as e:
        # 处理 API 调用失败的情况 (如消息超过2分钟)
        logger.error(f"撤回操作失败: {e}")
    except Exception as e:
        # 处理其他未知错误
        logger.error(f"发生错误: {e}")

from nonebot import logger, on_command
from nonebot.plugin import PluginMetadata
from nonebot.exception import FinishedException
from nonebot.adapters.onebot.v11 import GroupMessageEvent, Message, MessageSegment, Bot

from ...common.send_forward_msg import send_forward_msg
from .config import config
from . import utils
from . import core
from . import scheduler
from ...common.model.model import PluginGroupEnum, PluginBadgeColor

MESSAGE_SEPARATOR = config.fakemsg_user_split
FAKEMSG_CMD = config.fakemsg_cmd
MAX_DAILY_TIME = config.fakemsg_max_daily_time

__plugin_meta__ = PluginMetadata(
    name="消息伪造",
    description="伪造群友消息，支持自定义发送者昵称和QQ号发送合并转发消息",
    usage=f"伪消息 123456789 说内容\n伪消息 @用户 说内容\n多条消息用 {MESSAGE_SEPARATOR} 分隔\n\n管理命令（仅白名单用户）：\n- 伪消息 -ls  查看白名单\n- 伪消息 -add QQ号  添加白名单\n- 伪消息 -rm QQ号  移除白名单",
    supported_adapters={"~onebot.v11"},
    extra={
        "group": PluginGroupEnum.UTILITY.value,
        "badge_color": PluginBadgeColor.YELLOW.value
    }   
)

fakemsg = on_command(
    cmd=FAKEMSG_CMD,
    priority=30,
    block=False
)


@fakemsg.handle()
async def _(event: GroupMessageEvent, bot: Bot):
    raw_message = event.raw_message

    if '说' not in raw_message:
        cmd_result = core.process_command(raw_message, str(event.user_id))
        logger.info(cmd_result)
        if cmd_result is not None:
            await fakemsg.finish(cmd_result)
        return

    should_consume_quota = False

    try:
        scheduler.check_and_refresh_on_demand()

        person_users, group_users, daily_times_log = utils.get_plugin_config()
        person_users = [str(person_id) for person_id in person_users]
        group_users = [str(group_id) for group_id in group_users]
        logger.info(f"用户 {event.user_id} 在群 {event.group_id} 使用伪消息功能")

        is_plugin_user = False
        if str(event.group_id) in group_users or str(event.user_id) in person_users:
            is_plugin_user = True

        if not is_plugin_user:
            times = daily_times_log.get(str(event.user_id), 0)

            logger.info(f"用户 {event.user_id} 今日已使用 {times}/{MAX_DAILY_TIME} 次")
            if times >= MAX_DAILY_TIME:
                await fakemsg.finish(f"您已超过额度使用上限: {times}/{MAX_DAILY_TIME}")
            current_times = times

        await fakemsg.send("正在伪造消息...")

        original_message = event.original_message
        messages = core.extract_fake_messages(original_message)
        if not messages:
            logger.error("伪造消息失败")
            await fakemsg.finish(
                "伪造消息失败，请检查格式\n"
                "正确格式:\n"
                "• 伪消息 123456789 说内容\n"
                "• 伪消息 @用户 说内容\n"
                f"• 多条消息用 {config.fakemsg_user_split} 分隔"
            )

        if not is_plugin_user:
            bot_info = await utils.get_bot_info()
            bot_info.message = Message(
                f"本消息由 {MessageSegment.at(event.user_id)}({event.user_id}) 通过 Bot 生成\n"
                f"Bot 对消息内容概不负责\n"
                f"今日剩余额度: {MAX_DAILY_TIME - current_times - 1}/{MAX_DAILY_TIME}"
            )
            messages.append(bot_info)
            logger.info(f"伪造消息插件使用者: {event.sender.nickname}({event.sender.user_id}) 没有使用权限，将限制ta的使用次数，并自动插入默认消息")

        await send_forward_msg.custom_sender_by_onebot_api(bot=bot, event=event, senders_info=messages, group_id=str(event.group_id))

        should_consume_quota = True

    except FinishedException:
        pass
    except Exception as e:
        logger.error(f"伪消息插件报错：{e}")
        await fakemsg.finish(f"发送失败：{str(e)}")
    finally:
        if should_consume_quota and not is_plugin_user:
            utils.daily_times_addone(user_id=str(event.user_id))


scheduler.init_scheduler()

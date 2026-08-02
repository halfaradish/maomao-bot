from nonebot import logger, on_command, get_driver
from nonebot.plugin import PluginMetadata
from nonebot.exception import FinishedException
from nonebot.adapters.onebot.v11 import GroupMessageEvent, Message, MessageSegment, Bot
from sqlalchemy import select

from ...common.send_forward_msg import send_forward_msg
from ...common.database import async_session_factory
from ...common.permission import check_permission
from ...common.permission.models import PermissionGroup, PermissionGroupPerm
from .config import config
from . import utils
from . import core
from . import scheduler
from . import permissions  # noqa: F401 - 注册权限点到权限系统
from ...common.model.model import PluginGroupEnum, PluginBadgeColor

MESSAGE_SEPARATOR = config.fakemsg_user_split
FAKEMSG_CMD = config.fakemsg_cmd
MAX_DAILY_TIME = config.fakemsg_max_daily_time

__plugin_meta__ = PluginMetadata(
    name="消息伪造",
    description="伪造群友消息，支持自定义发送者昵称和QQ号发送合并转发消息",
    usage=(
        f"伪消息 123456789 说内容\n"
        f"伪消息 @用户 说内容\n"
        f"多条消息用 {MESSAGE_SEPARATOR} 分隔\n\n"
        f"管理命令（需 fakemsg:manage 权限）：\n"
        f"- 伪消息 -ls  查看白名单\n"
        f"- 伪消息 -add QQ号  添加白名单\n"
        f"- 伪消息 -rm QQ号  移除白名单\n\n"
        f"拥有 fakemsg:use 权限的用户可无限制使用，否则每日限额 {MAX_DAILY_TIME} 次。\n"
        f"权限可通过「权限」命令或 WebUI 管理面板配置。"
    ),
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
        cmd_result = await core.process_command(event)
        logger.info(cmd_result)
        if cmd_result is not None:
            await fakemsg.finish(cmd_result)
        return

    should_consume_quota = False
    is_plugin_user = False

    try:
        scheduler.check_and_refresh_on_demand()

        daily_times_log = utils.get_plugin_config()
        logger.info(f"用户 {event.user_id} 在群 {event.group_id} 使用伪消息功能")

        is_plugin_user = await check_permission(event, "fakemsg:use")

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


# ============================================================
# 启动钩子：自动创建 fakemsg 默认权限组
# ============================================================

@get_driver().on_startup
async def _ensure_default_perm_group():
    """确保 fakemsg 的默认权限组存在

    自动创建 fakemsg_users 权限组，包含 fakemsg:use 权限点。
    -add/-rm 命令操作此组的成员。已存在的权限组不会被重复创建。
    """
    async with async_session_factory() as session:
        existing = (await session.execute(
            select(PermissionGroup).where(PermissionGroup.name == core.DEFAULT_PG_NAME)
        )).scalars().first()
        if not existing:
            pg = PermissionGroup(
                name=core.DEFAULT_PG_NAME,
                display_name="伪消息白名单",
                description="自动创建：伪消息无限制使用权限组",
                created_by=0,  # 系统自动创建
            )
            session.add(pg)
            await session.flush()
            session.add(PermissionGroupPerm(group_id=pg.id, perm_key="fakemsg:use"))
            logger.info(f"[fakemsg] 自动创建权限组: {core.DEFAULT_PG_NAME}")
        await session.commit()


scheduler.init_scheduler()

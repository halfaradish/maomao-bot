from nonebot import Bot, get_bot, logger, get_plugin_config, on_command
from nonebot.plugin import PluginMetadata
from nonebot.adapters.onebot.v11 import GROUP, GroupMessageEvent, Message, MessageSegment
from nonebot.adapters.onebot.v11.exception import ActionFailed
from nonebot_plugin_apscheduler import scheduler

import re
import asyncio
from datetime import datetime, timedelta

from sqlalchemy import select, update as sa_update

from ...common.database import async_session_factory
from ...common.models.like_plugin_models import LikeRecord
from .config import Config
from src.common.model.model import PluginGroupEnum, PluginBadgeColor
from src.common.permission import check_permission, get_bound_group_ids

from . import permissions  # noqa: F401

plugin_config = get_plugin_config(Config)

__plugin_meta__ = PluginMetadata(
    name="点赞功能",
    description="NoneBot 的点赞功能，支持给自己和他人点赞，以及订阅每日点赞",
    usage="/赞我 -- 获取10个赞\n/赞他 @用户 -- 给指定用户点赞\n/订阅赞 -- 订阅每日点赞\n/取消订阅赞 -- 取消订阅每日点赞",
    config=Config,
    supported_adapters={ "~onebot.v11" },
    extra={
        "group": PluginGroupEnum.UTILITY.value,
        "badge_color": PluginBadgeColor.GREEN.value
    }
)

like_me = on_command(
    "赞我",
    permission=GROUP,
    priority=plugin_config.priority,
    block=plugin_config.block
)
like_other = on_command(
    "赞他",
    aliases={"赞她", "超市"},
    permission=GROUP,
    priority=plugin_config.priority,
    block=plugin_config.block
)
like_follow = on_command(
    "订阅赞",
    aliases={"dev-订阅赞"},
    permission=GROUP,
    priority=plugin_config.priority,
    block=plugin_config.block
)
like_unfollow = on_command(
    "取消订阅赞",
    permission=GROUP,
    priority=plugin_config.priority,
    block=plugin_config.block
)

# 试用订阅门槛：非权限用户需达到此群荣誉等级
TRIAL_REQUIRED_LEVEL = 15
# 试用订阅有效期（天）
TRIAL_DAYS = 7


async def follow_or_not(
    follow: bool,
    user_id: str,
    nickname: str,
    group_id: str | None = None,
    is_trial: bool = False,
) -> str:
    """改变订阅赞的用户状态

    Args:
        follow: True=订阅, False=取消订阅
        user_id: 用户 QQ 号
        nickname: 用户昵称
        group_id: 群号
        is_trial: 是否为试用订阅（True=7天有效期, False=永久）
    """
    try:
        async with async_session_factory() as session:
            stmt = select(LikeRecord).where(LikeRecord.user_id == user_id)
            result = await session.execute(stmt)
            obj = result.scalars().first()

            if follow and is_trial:
                trial_expires = datetime.now() + timedelta(days=TRIAL_DAYS)
                expires_str = trial_expires.strftime("%Y-%m-%d")
            else:
                trial_expires = None
                expires_str = None

            defaults = {
                "nickname": nickname,
                "is_following": follow,
                "trial_expires_at": trial_expires,
            }
            if group_id:
                defaults["group_number"] = str(group_id)

            if obj:
                for key, value in defaults.items():
                    setattr(obj, key, value)
                was_following = obj.is_following
                await session.commit()
                if follow:
                    if is_trial:
                        return f"试用订阅成功，有效期 {TRIAL_DAYS} 天（至 {expires_str}）"
                    else:
                        return "订阅成功" if not was_following else "您已订阅，无需再次订阅"
                else:
                    return "取消订阅成功" if was_following else "您未在订阅名单中，取消订阅失败"
            else:
                obj = LikeRecord(user_id=user_id, **defaults)
                session.add(obj)
                await session.commit()
                if follow:
                    if is_trial:
                        return f"试用订阅成功，有效期 {TRIAL_DAYS} 天（至 {expires_str}）"
                    else:
                        return "订阅成功"
                else:
                    return "取消订阅成功"
    except Exception as e:
        logger.opt(exception=True).error(f"用户 {user_id}: {nickname} 订阅时发生错误: {e}")
        return f"订阅操作失败，请稍后再试"


async def count_liked_times(user_id, count: int, nickname, group_id: str | None = None):
    """点赞次数计数"""
    async with async_session_factory() as session:
        stmt = select(LikeRecord).where(LikeRecord.user_id == user_id)
        result = await session.execute(stmt)
        obj = result.scalars().first()
        if obj:
            obj.nickname = nickname
            if group_id:
                obj.group_number = str(group_id)
        else:
            obj = LikeRecord(user_id=user_id, nickname=nickname)
            if group_id:
                obj.group_number = str(group_id)
            session.add(obj)
        await session.flush()

        stmt = (
            sa_update(LikeRecord)
            .where(LikeRecord.user_id == user_id)
            .values(
                count=LikeRecord.count + count,
                nickname=nickname,
            )
        )
        await session.execute(stmt)
        await session.commit()

async def send_like(bot: Bot, user_id) -> tuple[int, any]:
    """点赞函数"""
    count = 0
    err_msg = None
    try:
        for _ in range(5):
            await bot.call_api("send_like", **{
                "user_id": str(user_id),
                "times": plugin_config.like_time
            })
            count += 10
            logger.success(f"给 {user_id} 点赞成功, 当前点赞次数:{count}")
            await asyncio.sleep(1)
    except ActionFailed as e:
        logger.opt(exception=True).error(f"给 {user_id} 点赞 API 调用失败: {e}")
        err_msg = e.info
    except Exception as e:
        logger.opt(exception=True).error(f"给 {user_id} 点赞失败: {e}")
    return (count, err_msg)


async def _expire_trial_subscriptions():
    """将过期的试用订阅标记为取消"""
    now = datetime.now()
    async with async_session_factory() as session:
        stmt = (
            sa_update(LikeRecord)
            .where(
                LikeRecord.is_following == True,
                LikeRecord.trial_expires_at.is_not(None),
                LikeRecord.trial_expires_at < now,
            )
            .values(is_following=False)
        )
        result = await session.execute(stmt)
        await session.commit()
        expired_count = result.rowcount
        if expired_count > 0:
            logger.info(f"[点赞] 清理 {expired_count} 个过期试用订阅")
        return expired_count


@like_me.handle()
async def like_me_handle(bot: Bot, event: GroupMessageEvent):
    # 黑名单检查
    banned_groups = await get_bound_group_ids("like_ban")
    if event.group_id in banned_groups:
        await like_me.finish("❌ 本群未开启点赞功能")

    user_id = event.sender.user_id
    nickname = event.sender.nickname
    group_id = event.group_id

    if user_id:
        sender: Message = Message([MessageSegment.at(user_id=event.user_id)])
        count, err_msg = await send_like(bot=bot, user_id=user_id)
        if count > 0:
            await count_liked_times(user_id=user_id, count=count, nickname=nickname, group_id=str(group_id))
            await like_me.finish("已经给 " + sender + f" 点赞 {count} 次\n点赞的送达可能会有延迟, 如果失败了可以添加好友再试")
        else:
            if err_msg and isinstance(err_msg, dict) and err_msg.get("message") is not None and err_msg.get("message") != "":
                await like_me.finish(sender + err_msg.get("message"))
            else:
                await like_me.finish(sender + ", 给不了更多赞了哦")

@like_other.handle()
async def like_other_handle(bot: Bot, event: GroupMessageEvent):
    # 黑名单检查
    banned_groups = await get_bound_group_ids("like_ban")
    if event.group_id in banned_groups:
        await like_other.finish("❌ 本群未开启点赞功能")

    message = str(event.get_message()).strip()
    match = r"[1-9]([0-9]{5,11})"
    match_result = re.search(match, message)

    if not match_result:
        return

    user_id = int(match_result.group(0))
    user_info = await bot.get_stranger_info(user_id=int(user_id))
    nickname = user_info["nickname"]
    group_id = event.group_id

    if user_id:
        try:
            likeder: Message = Message([MessageSegment.at(user_id=user_id)])
            sender: Message = Message([MessageSegment.at(user_id=event.user_id)])
        except Exception as e:
            logger.error(f"获取@时出错: {e}")
            await bot.send(event=event, message="不是群里的人不赞")

        count, err_msg = await send_like(bot=bot, user_id=user_id)
        if count > 0:
            await count_liked_times(user_id=user_id, count=count, nickname=nickname, group_id=str(group_id))
            await like_other.finish("成功帮" + sender + " 给 " + likeder + f" 点赞 {count} 次")
        else:
            if err_msg and isinstance(err_msg, dict) and err_msg.get("message") is not None and err_msg.get("message") != "":
                await like_me.finish(sender + " " + err_msg.get("message"))
            else:
                await like_other.finish(sender + " , 无法给指定的人 " + likeder + " 更多赞了哦")

@like_follow.handle()
async def _(bot: Bot, event: GroupMessageEvent):
    user_id = event.sender.user_id
    nickname = event.sender.nickname
    group_id = event.group_id

    # 权限检查
    has_permission = await check_permission(event, "like:subscribe")

    if has_permission:
        # 权限通过 -> 永久订阅，无等级要求
        msg = f"收到订阅请求！用户: {nickname}({user_id})\n"
        msg += await follow_or_not(
            follow=True, user_id=str(user_id), nickname=nickname,
            group_id=str(group_id), is_trial=False
        )
        logger.info(msg)
        await bot.send(event, message=msg)
        return

    # 无权限 -> 检查群荣誉等级
    user_group_level = None
    try:
        member_info = await bot.get_group_member_info(
            group_id=group_id,
            user_id=user_id,
            no_cache=True
        )
        level_str = member_info.get('level', '0')
        user_group_level = int(level_str)
    except Exception as e:
        logger.warning(f"获取等级失败：{e}")
        user_group_level = None

    if user_group_level is not None and user_group_level < TRIAL_REQUIRED_LEVEL:
        await like_follow.finish(
            f"❌ 订阅失败：你的群荣誉等级为 {user_group_level}，"
            f"未达到要求的 {TRIAL_REQUIRED_LEVEL} 级（或无订阅权限）。"
        )

    # 等级达标 -> 试用订阅 7 天
    msg = f"收到订阅请求！用户: {nickname}({user_id})\n"
    msg += await follow_or_not(
        follow=True, user_id=str(user_id), nickname=nickname,
        group_id=str(group_id), is_trial=True
    )
    logger.info(msg)
    await bot.send(event, message=msg)

@like_unfollow.handle()
async def _(bot: Bot, event: GroupMessageEvent):
    follow: bool = False
    user_id = event.sender.user_id
    nickname = event.sender.nickname
    group_id = event.group_id
    logger.info(f"用户信息: user_id={user_id}, nickname={nickname}")

    msg = f"收到订阅请求！用户: {nickname}({user_id})\n"
    try:
        msg += await follow_or_not(follow=follow, user_id=str(user_id), nickname=nickname, group_id=str(group_id))
        logger.info(msg)
        await bot.send(event, message=msg)
    except Exception as e:
        logger.error(f"处理订阅时发生错误: {e}", exc_info=True)

@scheduler.scheduled_job("cron", hour=5, minute=0 ,second=0, id="job_subscribed_likes")
async def _():
    "给订阅的用户进行每日点赞"
    if not plugin_config.like_auto_send_like:
        return

    bot = get_bot()
    if not bot or not hasattr(bot, '_connected') or not bot._connected:
        logger.error("Bot 未连接，跳过定时点赞")
        return

    # 清理过期试用订阅
    await _expire_trial_subscriptions()

    async with async_session_factory() as session:
        stmt = select(LikeRecord).where(LikeRecord.is_following == True)
        result = await session.execute(stmt)
        subscribed_users = list(result.scalars().all())

    for user in subscribed_users:
        try:
            count, err_msg = await send_like(bot=bot, user_id=user.user_id)
            if count > 0:
                user_info = await bot.get_stranger_info(user_id=int(user.user_id))
                nickname = user_info["nickname"]
                async with async_session_factory() as session:
                    stmt = (
                        sa_update(LikeRecord)
                        .where(LikeRecord.user_id == user.user_id)
                        .values(
                            nickname=nickname,
                            count=LikeRecord.count + count,
                        )
                    )
                    await session.execute(stmt)
                    await session.commit()
            else:
                logger.error(err_msg)
        except Exception as e:
            logger.error(f"Error occurred while sending like to user {user.user_id}: {e}")
            continue
        finally:
            await asyncio.sleep(5)

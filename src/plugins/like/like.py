from nonebot import Bot, logger, get_plugin_config, on_regex, get_bot, on_command
from nonebot.plugin import PluginMetadata
from nonebot.adapters.onebot.v11 import GROUP, GroupMessageEvent, Message, MessageSegment
from nonebot.adapters.onebot.v11.exception import ActionFailed
from nonebot_plugin_apscheduler import scheduler

import re
import asyncio
from functools import wraps
from typing import Callable, List

from .config import Config
from ...common import JsonUtils
from src.common.model.model import PluginGroupEnum, PluginBadgeColor

plugin_config = get_plugin_config(Config)

__plugin_meta__ = PluginMetadata(
    name="点赞功能",
    description="NoneBot 的点赞功能，支持给自己和他人点赞，以及订阅每日点赞",
    usage="/赞我 —— 获取10个赞\n/赞他 @用户 —— 给指定用户点赞\n/订阅赞 —— 订阅每日点赞\n/取消订阅赞 —— 取消订阅每日点赞",
    config=Config,
    supported_adapters={ "~onebot.v11" },
    extra={
        "group": PluginGroupEnum.UTILITY.value,
        "badge_color": PluginBadgeColor.GREEN.value
    }
)

filename = plugin_config.data_filename

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

def perm_decorator(func: Callable) -> Callable:
    """
    权限装饰器，检查用户是否有权限
    """
    @wraps(func)
    async def wrapper(*args, **kwargs):
        logger.info("权限装饰器开始执行")
        
        # 从kwargs中获取event和bot（NoneBot通常通过依赖注入传递）
        event = kwargs.get('event')
        bot = kwargs.get('bot')
        
        # 如果kwargs中没有，则尝试从args中查找
        if not event or not bot:
            for arg in args:
                if isinstance(arg, GroupMessageEvent):
                    event = arg
                    logger.debug(f"从args中找到GroupMessageEvent参数，群ID: {event.group_id}")
                elif isinstance(arg, Bot):
                    bot = arg
                    logger.debug("从args中找到Bot参数")
        
        # logger.debug(f"wrapper接收到的参数 - args数量: {len(args)}, kwargs键: {list(kwargs.keys())}")
        # logger.debug(f"获取到的event: {event is not None}, bot: {bot is not None}")
        
        if not event or not bot:
            logger.warning("无法获取必要的event或bot参数")
            # 即使没有参数也尝试执行原函数，让NoneBot的错误处理机制介入
            return await func(*args, **kwargs)
        
        try:
            # 判断是否有权限
            data, _ = JsonUtils.read(filename, {
                "ban_group_users": []
            })
            ban_group_users: List = data.get('ban_group_users', [])
            logger.info(f"群ID: {event.group_id}，禁止列表: {ban_group_users}")
            
            if str(event.group_id) in ban_group_users:
                logger.info(f"群 {event.group_id} 没有权限使用该功能")
                return
            
            logger.info(f"群 {event.group_id} 有权限，继续执行原函数")
            # 有权限，返回原函数
            return await func(*args, **kwargs)
        except Exception as e:
            logger.error(f"权限检查过程中发生错误: {e}", exc_info=True)
            # 发生错误时也尝试执行原函数
            return
    
    return wrapper

def follow_or_not(follow: bool, user_id: str, nickname: str) -> str:
    """改变订阅赞的用户状态"""
    try:
        data, _ = JsonUtils.read(filename, {
            "liked_by_bot": {}
        })
        like_by_bot: dict = data.get("liked_by_bot", {})
        user_info = like_by_bot.setdefault(str(user_id), {
            "nickname": nickname,
            "count": 0,
            "follow": False
        })
        # 更新用户昵称（确保使用最新昵称）
        user_info["nickname"] = nickname
        
        if follow != user_info.get('follow', False):
            user_info['follow'] = follow  # 更新订阅状态
            JsonUtils.update(filename, {"liked_by_bot": like_by_bot})  # 保存更改
            
            if follow:
                return "订阅成功"
            else:
                return "取消订阅成功"
        else:
            if follow:
                return "您已订阅，无需再次订阅"
            else:
                return "您未在订阅名单中，取消订阅失败"
    except Exception as e:
        logger.opt(exception=True).error(f"用户 {user_id}: {nickname} 订阅时发生错误: {e}")
        return f"订阅操作失败，请稍后再试"

def count_liked_times(user_id, count: int, nickname):
    """
    点赞次数计数
    """
    # 加载数据
    data, _ = JsonUtils.read(filename, {
        "liked_by_bot": {}
    })
    liked_by_bot: dict = data.get("liked_by_bot", {})
    # 增加赞
    user = liked_by_bot.setdefault(str(user_id), {
        "nickname": nickname,
        "count": 0,
        "follow": False
    })
    user['nickname'] = nickname
    user['count'] += count
    JsonUtils.update(filename, {
        "liked_by_bot": liked_by_bot
    })
    

async def send_like(bot: Bot, user_id) -> tuple[int, any]:
    """
    点赞函数

    return
    点赞次数，错误信息
    """
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
    except ActionFailed as e:
        logger.opt(exception=True).error(f"给 {user_id} 点赞 API 调用失败: {e}")
        err_msg = e.info
    except Exception as e:
        logger.opt(exception=True).error(f"给 {user_id} 点赞失败: {e}")
    return (count, err_msg)

@like_me.handle()
async def like_me_handle(bot: Bot, event: GroupMessageEvent):
    user_id = event.sender.user_id
    nickname = event.sender.nickname

    if user_id:
        sender: Message = Message([MessageSegment.at(user_id=event.user_id)])
        count, err_msg = await send_like(bot=bot, user_id=user_id)
        if count > 0:
            count_liked_times(user_id=user_id, count=count, nickname=nickname)
            await like_me.finish("已经给 " + sender + f" 点赞 {count} 次\n点赞的送达可能会有延迟, 如果失败了可以添加好友再试")
        else:
            if err_msg and isinstance(err_msg, dict) and err_msg.get("message") is not None and err_msg.get("message") != "":
                await like_me.finish(sender + err_msg.get("message"))
            else:
                await like_me.finish(sender + ", 给不了更多赞了哦")

@like_other.handle()
async def like_other_handle(bot: Bot, event: GroupMessageEvent):
    """
    给别人点赞
    """
    message = str(event.get_message()).strip()
    match = r"[1-9]([0-9]{5,11})"

    match_result = re.search(match, message)

    if not match_result:
        return

    user_id = int(match_result.group(0))
    user_info = await bot.get_stranger_info(user_id=int(user_id))
    nickname = user_info["nickname"]

    if user_id:
        try:
            likeder: Message = Message([MessageSegment.at(user_id=user_id)])
            sender: Message = Message([MessageSegment.at(user_id=event.user_id)])
        except Exception as e:
            logger.error(f"获取@时出错: {e}")
            await bot.send(event=event, message="不是群里的人不赞")

        count, err_msg = await send_like(bot=bot, user_id=user_id)
        if count > 0:
            count_liked_times(user_id=user_id, count=count, nickname=nickname)
            await like_other.finish("成功帮" + sender + " 给 " + likeder + f" 点赞 {count} 次")
        else:
            if err_msg and isinstance(err_msg, dict) and err_msg.get("message") is not None and err_msg.get("message") != "":
                await like_me.finish(sender + " " + err_msg.get("message"))
            else:
                await like_other.finish(sender + " , 无法给指定的人 " + likeder + " 更多赞了哦")
    else:
        await like_other.finish(sender + "未指定有效的QQ号或@用户")

@like_follow.handle()
@perm_decorator
async def _(bot: Bot, event: GroupMessageEvent):
    follow: bool = True
    user_id = event.sender.user_id
    nickname = event.sender.nickname

    user_group_level = None 

    try:
        member_info = await bot.get_group_member_info(
            group_id=event.group_id,
            user_id=user_id,
            no_cache=True
        )
        level_str = member_info.get('level', '0')
        user_group_level = int(level_str)

    except Exception as e:
        logger.warning(f"获取等级失败，已自动放行：{e}")
        user_group_level = None

    REQUIRED_LEVEL = 10 #群等级门槛

    if user_group_level is not None and user_group_level < REQUIRED_LEVEL:
        await like_follow.finish(f"❌ 订阅失败：你的群荣誉等级为 {user_group_level}，未达到要求的 {REQUIRED_LEVEL} 级。")

   
    msg = f"收到订阅请求！用户: {nickname}({user_id})\n"
    msg += follow_or_not(follow=follow, user_id=str(user_id), nickname=nickname)

    logger.info(msg)
    await bot.send(event, message=msg)

@like_unfollow.handle()
async def _(bot: Bot, event: GroupMessageEvent):
    """取消订阅"""
    follow: bool = False
    user_id = event.sender.user_id
    nickname = event.sender.nickname
    logger.info(f"用户信息: user_id={user_id}, nickname={nickname}")

    msg = f"收到订阅请求！用户: {nickname}({user_id})\n"
    try:
        msg += follow_or_not(follow=follow, user_id=str(user_id), nickname=nickname)
        logger.info(msg)
        await bot.send(event, message=msg)
    except Exception as e:
        logger.error(f"处理订阅时发生错误: {e}", exc_info=True)

@scheduler.scheduled_job("cron", hour=5, minute=0 ,second=0, id="job_subscribed_likes")
async def _():
    "给订阅的用户进行每日点赞"
    if not plugin_config.like_auto_send_like:
        return
    # 获取数据
    bot = get_bot()
    data, _ = JsonUtils.read(filename, {
        "liked_by_bot": {}
    })
    liked_by_bot: dict = data.get("liked_by_bot", {})
    # 为订阅的用户点赞
    for user_id, user_info in liked_by_bot.items():
        if user_info['follow']:
            try:
                count, err_msg = await send_like(bot=bot, user_id=user_id)
                if count > 0:
                    user_info = await bot.get_stranger_info(user_id=int(user_id))
                    nickname = user_info["nickname"]
                    count_liked_times(user_id=user_id, count=count, nickname=nickname)
                    liked_by_bot[user_id]['nickname'] = nickname
                    liked_by_bot[user_id]['count'] += count
                else:
                    logger.error(err_msg)
            except Exception as e:
                logger.error(f"Error occurred while sending like to user {user_id}: {e}")
                continue
            finally:
                await asyncio.sleep(5)
    # 存入数据
    JsonUtils.update(filename, {
        "liked_by_bot": liked_by_bot
    })

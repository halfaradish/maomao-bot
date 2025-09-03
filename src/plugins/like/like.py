from nonebot import Bot, on_command, logger, get_plugin_config, on_regex, get_bot
from nonebot.plugin import PluginMetadata
from nonebot.adapters.onebot.v11 import GROUP, GroupMessageEvent, Message, MessageSegment
from nonebot.adapters.onebot.v11.exception import ActionFailed
from nonebot_plugin_apscheduler import scheduler

import re

from .config import Config
from ...common import JsonUtils

plugin_config = get_plugin_config(Config)

__plugin_meta__ = PluginMetadata(
    name="like",
    description="NoneBot 的点赞功能",
    usage="发送 '/赞我' 获取10个赞",
    config=Config,
    supported_adapters={ "~onebot.v11" }
)

filename = plugin_config.data_filename

like_me = on_regex(
    "^(超|赞)(市|)我$",
    permission=GROUP,
    priority=plugin_config.priority,
    block=plugin_config.block
)
like_other = on_regex(
    "^(超|赞)(市|)(你|他|她|它|TA|)\s*(.*)$",
    permission=GROUP,
    priority=plugin_config.priority,
    block=plugin_config.block
)
like_follow = on_regex(
    r"^^(?:天天.+我|订阅赞)$$",
    permission=GROUP,
    priority=plugin_config.priority,
    block=plugin_config.block
)
like_unfollow = on_regex(
    r"^(?:不要?|补药|取消)\s*(?:天天.我|订阅赞)$",
    permission=GROUP,
    priority=plugin_config.priority,
    block=plugin_config.block
)

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
        count, err_msg = await send_like(event=event, bot=bot, user_id=user_id)
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

        count, err_msg = await send_like(event=event, bot=bot, user_id=user_id)
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
async def _(bot: Bot, event: GroupMessageEvent):
    """添加订阅"""
    follow: bool = True
    user_id = event.sender.user_id
    nickname = event.sender.nickname
    msg = follow_or_not(follow=follow, user_id=user_id, nickname=nickname)
    await like_unfollow.finish(msg)

@like_unfollow.handle()
async def _(bot: Bot, event: GroupMessageEvent):
    """取消订阅"""
    follow: bool = False
    user_id = event.sender.user_id
    nickname = event.sender.nickname
    msg = follow_or_not(follow=follow, user_id=user_id, nickname=nickname)
    await like_unfollow.finish(msg)

@scheduler.scheduled_job("cron", hour=6, minute=0 ,second=0, id="job_subscribed_likes")
async def _():
    "给订阅的用户进行每日点赞"
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
    # 存入数据
    JsonUtils.update(filename, {
        "liked_by_bot": liked_by_bot
    })

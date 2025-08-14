from nonebot import Bot, on_command, logger, get_plugin_config, on_regex
from nonebot.plugin import PluginMetadata
from nonebot.adapters.onebot.v11 import GROUP, GroupMessageEvent, Message, MessageSegment
from nonebot.adapters.onebot.v11.exception import ActionFailed
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

def count_liked_times(user_id, count: int):
    """
    点赞次数计数
    """
    # 加载数据
    data, _ = JsonUtils.read(filename, {
        "follow": {},
        "quick_list": []
    })
    follow, quick_list = data.get("follow", {}), data.get("quick_list", [])
    # 增加赞
    if user_id not in quick_list:
        quick_list.append(user_id)
        follow[str(user_id)] = 0
    follow[str(user_id)] += count
    # 更新数据
    JsonUtils.update(filename, {
        "follow": follow,
        "quick_list": quick_list
    })

async def send_like(event: GroupMessageEvent, bot: Bot, user_id) -> tuple[int, any]:
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
    user_id = event.user_id

    if user_id:
        sender: Message = Message([MessageSegment.at(user_id=event.user_id)])
        count, err_msg = await send_like(event=event, bot=bot, user_id=user_id)
        if count > 0:
            count_liked_times(user_id=user_id, count=count)
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

    if user_id:
        try:
            likeder: Message = Message([MessageSegment.at(user_id=user_id)])
            sender: Message = Message([MessageSegment.at(user_id=event.user_id)])
        except Exception as e:
            logger.error(f"获取@时出错: {e}")
            await bot.send(event=event, message="不是群里的人不赞")

        count, err_msg = await send_like(event=event, bot=bot, user_id=user_id)
        if count > 0:
            count_liked_times(user_id=user_id, count=count)
            await like_other.finish("成功帮" + sender + " 给 " + likeder + f" 点赞 {count} 次")
        else:
            if err_msg and isinstance(err_msg, dict) and err_msg.get("message") is not None and err_msg.get("message") != "":
                await like_me.finish(sender + " " + err_msg.get("message"))
            else:
                await like_other.finish(sender + " , 无法给指定的人 " + likeder + " 更多赞了哦")
    else:
        await like_other.finish(sender + "未指定有效的QQ号或@用户")
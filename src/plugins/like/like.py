from nonebot import Bot, on_command, get_driver, logger
from nonebot.plugin import PluginMetadata
from nonebot.adapters.onebot.v11 import MessageEvent

from .config import Config

global_config = get_driver().config
plugin_config = Config.parse_obj(global_config.dict())

__plugin_meta__ = PluginMetadata(
    name="like",
    description="NoneBot 的点赞功能",
    usage="发送 '/赞我' 获取10个赞",
    config=Config,
    supported_adapters={ "~onebot.v11" }
)

like_command = on_command(
    "赞我",
    aliases={"超我", "超市我", "点赞"},
    priority=10,
    block=True
)

@like_command.handle()
async def like_handle(bot: Bot, event: MessageEvent):
    user_id = event.user_id

    try:
        # 尝试给指定用户点赞 50 次
        for i in range(5):
            await bot.call_api("send_like", **{
                "user_id": str(user_id),
                "times": plugin_config.like_time
            })
            count += 10
            logger.opt(exception=True).info(f"给 {event.sender.user_id} 点赞成功, 当前点赞次数:{count}")

        # 判断是否点赞成功
        if count != 0:
            await bot.send(event=event, message=f"已经给 '{event.sender.nickname}' 点赞 {count} 次\n点赞的送达可能会有延迟, 如果失败了可以添加好友再试")
        else:
            await bot.send(event=event, message=f"'{event.sender.nickname}' , 给不了更多赞了哦")
    except Exception as e:
        logger.opt(exception=True).error(f"给 {event.sender.nickname}: {event.sender.user_id} 点赞失败: {e}")

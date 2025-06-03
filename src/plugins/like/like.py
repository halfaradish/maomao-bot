from nonebot import Bot, on_command
from nonebot.plugin import PluginMetadata
from nonebot.adapters.onebot.v11 import MessageEvent, GroupMessageEvent, PrivateMessageEvent

from .config import Config

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
        await bot.call_api("send_like", **{
            "user_id": str(user_id),
            "times": 10
        })

        await bot.send(event=event, message=f"✅ 成功点赞, 10个赞收好")
    except Exception as e:
        await bot.send(event=event, message=f"❌ 点赞失败, 今日已达上限")
from nonebot import logger
from nonebot.adapters.onebot.v11 import (
    Bot,
    MessageEvent,
    GroupMessageEvent,
    PrivateMessageEvent,
    Message
)
from typing import List, overload

class SendForwardMsg:
    @overload
    async def by_onebot_api(
        bot: Bot,
        event: GroupMessageEvent,
        messges: List,
        *,
        group_id: str,
        user_id: None = None
    ) -> None: ...

    @overload
    async def by_onebot_api(
        bot: Bot,
        event: PrivateMessageEvent,
        messges: List,
        *,
        group_id: None = None,
        user_id: str
    ) -> None: ...

    @staticmethod
    async def by_onebot_api(
        bot: Bot,
        event: MessageEvent,
        messges: List,
        group_id: str | None = None,
        user_id: str | None = None
    ) -> None:
        """
        通过 OneBot v11 API 发送合并转发消息。

        根据事件类型自动选择发送目标，并要求提供对应的 ID：
        - 群聊事件 → 必须提供 group_id
        - 私聊事件 → 必须提供 user_id

        参数:
            bot: 机器人实例。
            event: 消息事件（GroupMessageEvent 或 PrivateMessageEvent）。
            messages: 要转发的消息文本列表。
            group_id: 群号（仅群聊时提供）。
            user_id: 用户 QQ 号（仅私聊时提供）。

        Raises:
            ValueError: 当参数与事件类型不匹配时。
        """
        def to_node(name: str, uin: str, message: Message):
            """构建统一的格式"""
            return {
                "type": "node",
                "data": {"name": name, "uin": uin, "content": message},
            }
        
        # 获取机器人自身信息
        info = await bot.get_login_info()
        name = info['nickname']
        uin = bot.self_id
        
        # 构建消息节点
        message_nodes = [to_node(name=name, uin=uin, message=Message(message)) for message in messges]

        if isinstance(event, GroupMessageEvent):
            if group_id is None:
                raise ValueError("group_id is required for group messages.")
            await bot.call_api("send_group_forward_msg", group_id=group_id, messages=message_nodes)
        elif isinstance(event, PrivateMessageEvent):
            if user_id is None:
                raise ValueError("user_id is required for private messages.")
            await bot.call_api("send_private_forward_msg", user_id=user_id, messages=message_nodes)
        else:
            raise TypeError("Unsupported message event type.")
    
    @staticmethod
    async def by_napcat_api(
        messages: List[str],
        prompt: str = "prompt",
        summary: str = "查看聊天消息",
        source: str = "群聊的聊天消息",
        news: List[str] = ["查看记录"]
    ):
        return

send_forword_msg = SendForwardMsg()

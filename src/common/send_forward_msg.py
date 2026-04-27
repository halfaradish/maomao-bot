from nonebot import logger
from nonebot.adapters.onebot.v11 import (
    Bot,
    MessageEvent,
    GroupMessageEvent,
    PrivateMessageEvent,
    Message
)
from typing import List, overload
from dataclasses import dataclass

@dataclass
class SenderInfo:
    user_id: str    # 自定义发送者QQ号
    nickname: str  # 自定义发送者昵称
    message: Message  # 自定义发送者的消息内容

class SendForwardMsg:
    # 抽离为公共静态方法：构建转发消息节点
    @staticmethod
    def to_node(name: str, uin: str, message: Message) -> dict:
        """构建 OneBot 合并转发节点格式"""
        return {
            "type": "node",
            "data": {"name": name, "uin": uin, "content": message},
        }

    @overload
    async def by_onebot_api(
        self,
        bot: Bot,
        event: GroupMessageEvent,
        messges: List,
        *,
        group_id: str,
        user_id: None = None
    ) -> None: ...

    @overload
    async def by_onebot_api(
        self,
        bot: Bot,
        event: PrivateMessageEvent,
        messges: List,
        *,
        group_id: None = None,
        user_id: str
    ) -> None: ...

    async def by_onebot_api(
        self,
        bot: Bot,
        event: MessageEvent,
        messges: List,
        group_id: str | None = None,
        user_id: str | None = None
    ) -> None:
        """
        通过 OneBot v11 API 发送合并转发消息（使用机器人自身信息）
        """
        # 获取机器人自身信息
        info = await bot.get_login_info()
        name = info['nickname']
        uin = bot.self_id
        
        # 构建消息节点
        message_nodes = [self.to_node(name=name, uin=uin, message=Message(message)) for message in messges]

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

    # ====================== 新增：自定义发送者合并转发函数 ======================
    async def custom_sender_by_onebot_api(
        self,
        bot: Bot,
        event: MessageEvent,
        senders_info: List[SenderInfo],
        group_id: str | None = None,
        user_id: str | None = None
    ) -> None:
        """
        通过 OneBot v11 API 发送【自定义发送者】合并转发消息
        每条消息的发送者昵称、QQ号完全由传入的 SenderInfo 定义，不使用机器人自身信息

        参数:
            bot: 机器人实例
            event: 消息事件（GroupMessageEvent/PrivateMessageEvent）
            senders_info: 自定义发送者信息列表
            group_id: 目标群号（群聊场景必填）
            user_id: 目标用户QQ（私聊场景必填）

        Raises:
            ValueError: 群聊未传group_id / 私聊未传user_id
            TypeError: 不支持的事件类型
        """
        # 遍历自定义发送者列表，构建转发节点
        message_nodes = [
            self.to_node(
                name=sender.nickname,
                uin=sender.user_id,
                message=sender.message
            )
            for sender in senders_info
        ]

        # 群聊/私聊分发调用API
        if isinstance(event, GroupMessageEvent):
            if not group_id:
                raise ValueError("群聊发送合并转发必须传入 group_id")
            await bot.call_api(
                "send_group_forward_msg",
                group_id=group_id,
                messages=message_nodes
            )

        elif isinstance(event, PrivateMessageEvent):
            if not user_id:
                raise ValueError("私聊发送合并转发必须传入 user_id")
            await bot.call_api(
                "send_private_forward_msg",
                user_id=user_id,
                messages=message_nodes
            )

        else:
            raise TypeError("仅支持群聊/私聊消息事件")

    @staticmethod
    async def by_napcat_api(
        messages: List[str],
        prompt: str = "prompt",
        summary: str = "查看聊天消息",
        source: str = "群聊的聊天消息",
        news: List[str] = ["查看记录"]
    ):
        return

send_forward_msg = SendForwardMsg()
from nonebot import on_command, logger, get_plugin_config
from nonebot.adapters import Bot, Message
from nonebot.adapters.onebot.v11 import GROUP, GroupMessageEvent, Event
from nonebot.plugin import PluginMetadata
from nonebot.params import CommandArg
from typing import List

from .config import Config
from ...common import JsonUtils

plugin_config = get_plugin_config(Config)

__plugin_meta__ = PluginMetadata(
    name="搬史小助手",
    description="",
    usage="",
    config=Config,
)

transport_manual = on_command(
    "搬史",
    aliases={"搬屎", "转发"},
    priority=plugin_config.priority,
    block=plugin_config.block
)

def get_forward_groups() -> List[int]:
    """获取转发的群列表"""
    filename = plugin_config.data_filename
    content = []
    content, _= JsonUtils.read(filename, {})

    return content['forward_groups']

def build_forward_node(nickname: str, user_id: str, content: list[dict]) -> dict:
    """构建转发消息的格式"""
    return {
        "type": "node",
        "data": {
            "nickname": nickname,
            "user_id": str(user_id),
            "content": content
        }
    }

def conversion_forward_msg(messages: list[dict]) -> list[dict]:
    """构建转发消息的格式"""
    forward_messages = []
    for msg in messages:
        if "sender" in msg and "message" in msg:
            if msg["message"][0].get("type") == "forward":
                forward_messages.append(
                    build_forward_node(
                        nickname=msg["sender"].get("nickname", "未知用户"),
                        user_id=str(msg["sender"].get("user_id", "")),
                        content=conversion_forward_msg(msg["message"][0].get("data", {}).get("content", []))
                    )
                )
                continue
            forward_messages.append(
                build_forward_node(
                    nickname=msg["sender"].get("nickname", "未知用户"),
                    user_id=str(msg["sender"].get("user_id", "")),
                    content=msg["message"][0]
                )
            )
    return forward_messages

@transport_manual.handle()
async def _(bot: Bot, event: GroupMessageEvent, args: Message = CommandArg()):
    raw_args = args.extract_plain_text().strip()
    params = raw_args.split() if raw_args else []
    try:
        # 如果没有参数
        if not params:
            # 如果没有引用的消息
            if not event.reply:
                await bot.send(event=event, message=plugin_config.DEFAULT_MSG)
                return
            
            forward_msg = await bot.call_api(
                "get_forward_msg",
                message_id=event.reply.message_id,
            )

            # 获取当前引用的消息的群组ID
            source_group_id = event.group_id

            # 重构消息节点时添加字段检查
            messages = conversion_forward_msg(forward_msg.get("messages", []))

            # 获取转发的群组列表
            forward_groups = get_forward_groups()
            if not forward_groups:
                logger.warning(f"空转发群组列表 (用户:{event.user_id} 群组:{event.group_id})")
                await bot.send(event=event, message="没有配置转发的群组")
                return

            # 转发消息
            success_count = 0
            error_groups = []
            for group_id in forward_groups:
                if group_id == source_group_id:
                    continue
                try:
                    await bot.call_api(
                        "send_group_forward_msg",
                        group_id=group_id,
                        messages=[{"type": "node", "data": msg} for msg in messages]  # 显式指定消息类型
                    )
                    success_count += 1
                except Exception as e:
                    logger.error(f"转发消息到群 {group_id} 失败: {e}")
                    error_groups.append(str(group_id))

            result_msg = f"已成功转发到 {success_count} 个群组"
            if error_groups:
                result_msg += f"\n以下群组发送失败: {', '.join(error_groups)}"
            await bot.send(event=event, message=result_msg)

        elif params[0].lower() in ["list", "ls", "查看", "查询"]:
            """查看转发的群列表"""
            forward_groups = get_forward_groups()
            if not forward_groups:
                await bot.send(event=event, message="没有配置转发的群组")
                return
            
            group_list = "\n".join([f"群号: {group_id}" for group_id in forward_groups])
            await bot.send(event=event, message=f"当前配置的转发群组:\n{group_list}")
        elif params[0].lower() in ["add", "添加", "增加"]:
            """添加转发的群"""
            if len(params) < 2 or not params[1].isdigit():
                await bot.send(event=event, message="请提供合法的群号")
                return
            
            group_id = int(params[1])
            forward_groups = get_forward_groups()
            if group_id in forward_groups:
                await bot.send(event=event, message=f"群 {group_id} 已经在转发列表中")
                return
            
            forward_groups.append(group_id)
            JsonUtils.update(plugin_config.data_filename, {"forward_groups": forward_groups})
            await bot.send(event=event, message=f"已将群 {group_id} 添加到转发列表")
            return
        elif params[0].lower() in ["remove", "rm", "删除", "移除"]:
            """删除转发的群"""
            if len(params) < 2 or not params[1].isdigit():
                await bot.send(event=event, message="请提供合法的群号")
                return
            
            group_id = int(params[1])
            forward_groups = get_forward_groups()
            if group_id not in forward_groups:
                await bot.send(event=event, message=f"群 {group_id} 不在转发列表中")
                return
            
            forward_groups.remove(group_id)
            JsonUtils.update(plugin_config.data_filename, {"forward_groups": forward_groups})
            await bot.send(event=event, message=f"已将群 {group_id} 从转发列表中移除")
            return
        else:
            await bot.send(event=event, message="无效的参数, 请使用 '/搬史' 查看帮助")
            return
    except Exception as e:
        logger.error(f"搬史小助手发生错误: {e}")
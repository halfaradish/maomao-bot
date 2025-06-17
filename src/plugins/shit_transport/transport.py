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
    aliases={"搬", "搬屎", "转发"},
    priority=plugin_config.priority,
    block=plugin_config.block
)

def get_forward_groups() -> List[int]:
    """获取转发的群列表"""
    filename = plugin_config.data_filename
    content = []
    content, _= JsonUtils.read(filename, {})

    return content['forward_groups']

@transport_manual.handle()
async def _(bot: Bot, evnet: GroupMessageEvent, args: Message = CommandArg()):
    raw_args = args.extract_plain_text().strip()
    params = raw_args.split() if raw_args else []
    try:
        # 如果没有参数
        if not params:
            if not evnet.reply:
                await bot.send(event=evnet, message=plugin_config.DEFAULT_MSG)
                return
            
            # 获取当前引用的消息的群组ID
            source_group_id = evnet.group_id

            forward_msg = await bot.call_api(
                "get_forward_msg",
                message_id=evnet.reply.message_id,
            )

            # 重构消息节点
            messages = [
                {
                    "type": "node",
                    "data": {
                        "name": msg["sender"]["nickname"],
                        "uin": msg["sender"]["user_id"],
                        "content": msg["content"]
                    }
                }
                for msg in forward_msg["messages"]
            ]

            forward_groups = get_forward_groups()
            if not forward_groups:
                await bot.send(event=evnet, message="没有配置转发的群组")
                return

            for group_id in forward_groups:
                if group_id == source_group_id:
                    continue
                await bot.call_api(
                    "send_group_forward_msg",
                    group_id=group_id,
                    messages=messages  # 使用重构后的消息结构
                )
        elif params[0].lower() in ["list", "ls", "查看", "查询"]:
            """查看转发的群列表"""
            forward_groups = get_forward_groups()
            if not forward_groups:
                await bot.send(event=evnet, message="没有配置转发的群组")
                return
            
            group_list = "\n".join([f"群号: {group_id}" for group_id in forward_groups])
            await bot.send(event=evnet, message=f"当前配置的转发群组:\n{group_list}")
        elif params[0].lower() in ["add", "添加", "增加"]:
            """添加转发的群"""
            if len(params) < 2 or not params[1].isdigit():
                await bot.send(event=evnet, message="请提供合法的群号")
                return
            
            group_id = int(params[1])
            forward_groups = get_forward_groups()
            if group_id in forward_groups:
                await bot.send(event=evnet, message=f"群 {group_id} 已经在转发列表中")
                return
            
            forward_groups.append(group_id)
            JsonUtils.update(plugin_config.data_filename, {"forward_groups": forward_groups})
            await bot.send(event=evnet, message=f"已将群 {group_id} 添加到转发列表")
            return
        elif params[0].lower() in ["remove", "rm", "删除", "移除"]:
            """删除转发的群"""
            if len(params) < 2 or not params[1].isdigit():
                await bot.send(event=evnet, message="请提供合法的群号")
                return
            
            group_id = int(params[1])
            forward_groups = get_forward_groups()
            if group_id not in forward_groups:
                await bot.send(event=evnet, message=f"群 {group_id} 不在转发列表中")
                return
            
            forward_groups.remove(group_id)
            JsonUtils.update(plugin_config.data_filename, {"forward_groups": forward_groups})
            await bot.send(event=evnet, message=f"已将群 {group_id} 从转发列表中移除")
            return
        else:
            await bot.send(event=evnet, message="无效的参数, 请使用 '/搬史' 查看帮助")
            return
    except Exception as e:
        logger.error(f"搬史小助手发生错误: {e}")
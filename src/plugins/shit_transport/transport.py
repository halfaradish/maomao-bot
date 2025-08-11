from nonebot import on_command, logger, get_plugin_config
from nonebot.adapters.onebot.v11 import GROUP, GroupMessageEvent, Event, Message, Bot, MessageEvent
from nonebot.plugin import PluginMetadata
from nonebot.params import CommandArg
from typing import List
import json
import http.client

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
    content, _= JsonUtils.read(filename, {"forward_groups": []})

    return content['forward_groups']

def is_forwarded_message(event: MessageEvent) -> bool:
    # 检查消息段列表
    for segment in event.reply.message:
        # 1. 判断是否为 JSON 类型消息段
        if segment.type == "json" or "forward":
            return True
    return False

def forward_group_single_msg(group_id: int, message_id) -> None:
    """转发消息"""
    conn = http.client.HTTPConnection(plugin_config.api_host, plugin_config.api_port)
    headers = {
        'Content-Type': 'application/json',
        'Authorization': plugin_config.api_tokne
    }
    payload = json.dumps({
        "group_id": group_id,
        "message_id": message_id
    })
    try:
        conn.request("POST", "/forward_group_single_msg", payload, headers)
        res = conn.getresponse()
        logger.info(res.read().decode())
    except Exception as e:
        logger.opt(exception=True).error(f"转发消息到{str(message_id)}时出错: {e}")
    finally:
        conn.close()

async def send_group_text_msg(group_id: int, bot: Bot) -> None:
    """发送默认消息"""
    payload = {
        "group_id": group_id,
        "message": [
            {
                "type": "text",
                "data": {
                    "text": "以下信息由 搬史小助手 负责转发"
                }
            }
        ]
    }
    await bot.call_api("send_group_msg", **payload)
    
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
            message_id = event.reply.message_id
            # logger.info(f"event type is: {event.get_type}")
            # logger.info(message_id)
            # logger.info(f"reply message: {event.reply}")

            if not is_forwarded_message(event=event):
                await bot.send(event=event, message="bot只转发合并转发消息")
                return

            # 获取消息出现的群组
            source_group_id = event.group_id
            # 获取要转发的群组
            forward_groups: list[int] = get_forward_groups()
            if not forward_groups:
                logger.warning(f"空转发群组列表 (用户:{event.user_id} 群组:{event.group_id})")
                await bot.send(event=event, message="没有配置转发的群组")
                return
            
            # 转发消息
            success_cnt = 0
            error_groups = []
            for group_id in forward_groups:
                # 如果要转发的群组包含当前群组
                if group_id == source_group_id:
                    continue
                # 发送消息
                try:
                    forward_group_single_msg(group_id=group_id, message_id=message_id)
                    success_cnt += 1
                    await send_group_text_msg(group_id=group_id, bot=bot)
                except Exception as e:
                    error_groups.append(group_id)
            
            # 回复结果
            result_msg = f"已成功转发到 {success_cnt} 个群组"
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
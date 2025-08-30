from nonebot import on_command, logger, get_plugin_config
from nonebot.adapters.onebot.v11 import GROUP, GroupMessageEvent, Event, Message, Bot, MessageEvent
from nonebot.plugin import PluginMetadata
from nonebot.params import CommandArg
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
    aliases={"搬屎", "转发", "banshi", "bs"},
    priority=plugin_config.priority,
    block=plugin_config.block
)

def get_forward_groups() -> list[dict]:
    """获取转发的群列表"""
    filename = plugin_config.data_filename
    content = []
    content, _= JsonUtils.read(filename, {"forward_groups": []})

    return content['forward_groups']

def forward_group_single_msg(group_id: int, message_id) -> None:
    """转发消息"""
    conn = http.client.HTTPConnection(plugin_config.api_host, plugin_config.api_port)
    headers = {
        'Content-Type': 'application/json',
        'Authorization': plugin_config.api_token
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
                    "text": "该信息由 搬史小助手 负责转发"
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

            # 获取消息出现的群组
            source_group_id = event.group_id
            # 获取要转发的群组
            data, _= JsonUtils.read(plugin_config.data_filename, {
                "forward_groups": [],
                "frequency_statistics": {}
            })
            forward_groups: list[dict] = data['forward_groups']
            if not forward_groups:
                logger.warning(f"空转发群组列表 (用户:{event.user_id} 群组:{event.group_id})")
                await bot.send(event=event, message="没有配置转发的群组")
                return
            
            # 转发消息
            success_cnt = 0
            error_groups = []
            for forward_group in forward_groups:
                group_id = forward_group["group_id"]
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
            
            # 统计使用该插件的人的使用次数
            freq: dict = data["frequency_statistics"]
            freq[str(event.sender.user_id)] = {
                "count": freq.get(str(event.sender.user_id), {}).get("count", 0) + 1,
                "nickname": event.sender.nickname
            }
            JsonUtils.update(plugin_config.data_filename, {
                "frequency_statistics": freq
            })

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
            
            group_list = "\n".join(f"群号：{forward_group['group_id']}  群名：{forward_group['group_name']}" for forward_group in forward_groups)
            await bot.send(event=event, message=f"当前配置的转发群组:\n{group_list}")
        elif params[0].lower() in ["add", "添加", "增加"]:
            """添加转发的群"""
            if len(params) < 2 or not params[1].isdigit():
                await bot.send(event=event, message="请提供合法的群号")
                return

            group_id = int(params[1])

            # 查看是否在被指定的群组group_id里
            exists_groups_list = await bot.call_api("get_group_list")
            group_info = next((group_msg for group_msg in exists_groups_list if group_msg["group_id"] == group_id), None)
            if not group_info:
                await transport_manual.finish(f"bot 还未加入群组 {group_id} 中")

            # 查看是否已在群组转发列表里
            forward_groups = get_forward_groups()
            configured = any(forward_group["group_id"] == group_id for forward_group in forward_groups)
            if configured:
                await bot.send(event=event, message=f"群 {group_id} 已经在转发列表中")
                return
            
            forward_groups.append(group_info)
            JsonUtils.update(plugin_config.data_filename, {"forward_groups": forward_groups})
            await bot.send(event=event, message=f"已将群 {group_id} 添加到转发列表")
            return
        elif params[0].lower() in ["remove", "rm", "删除", "移除"]:
            """删除转发的群"""
            if len(params) < 2 or not params[1].isdigit():
                await bot.send(event=event, message="请提供合法的群号")
                return
            
            group_id = int(params[1])
            configured: bool = True
            forward_groups = get_forward_groups()
            for i, forward_group in enumerate(forward_groups):
                if forward_group["group_id"] == group_id:
                    configured = False
                    del forward_groups[i]
                    break
            
            # 如果群不在群列表中
            if configured:
                transport_manual.finish(f"群 {group_id} 不在转发列表中")

            JsonUtils.update(plugin_config.data_filename, {"forward_groups": forward_groups})
            await bot.send(event=event, message=f"已将群 {group_id} 从转发列表中移除")
            return
        elif params[0].lower() in ["count", "计数", "统计"]:
            """展示使用该插件的人的使用次数"""
            data, _= JsonUtils.read(plugin_config.data_filename, {
                "forward_groups": [],
                "frequency_statistics": {}
            })
            freq: dict = data["frequency_statistics"]

            res_msg = "搬史插件使用次数统计:"
            if not freq:
                await transport_manual.finish(res_msg + "\n无使用记录")
            for user_info in freq.values():
                res_msg += f"\n{user_info['nickname']} 搬史 {user_info['count']} 次"

            await transport_manual.finish(res_msg)
        # else:
        #     await bot.send(event=event, message="无效的参数, 请使用 '/搬史' 查看帮助")
        #     return
    except Exception as e:
        logger.error(f"搬史小助手发生错误: {e}")
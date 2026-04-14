from nonebot import on_command, logger
from nonebot.adapters.onebot.v11 import Bot, MessageEvent, GroupMessageEvent
from nonebot.params import CommandArg
from nonebot.adapters import Message
from nonebot.plugin import PluginMetadata
from nonebot import get_driver

import http.client
import json

from .config import Config
from ...config.local_config import QQControlConfig
from ..cmd_list.model import PluginGroupEnum

__plugin_meta__ = PluginMetadata(
    name="分组发送",
    description="分组发送插件，向指定分组的所有成员发送消息（支持文本和图片）",
    usage="回复要发送的消息，然后使用：分组发送 分组名\n支持发送文本、图片等富媒体内容",
    config=Config,
    supported_adapters={"~onebot.v11"},
    extra={
        "group": PluginGroupEnum.GROUP_MANAGE.value,
        "badge_color": "blue"
    }
)

from ..group_manager import _get_group_detail


# API配置
api_host: str = QQControlConfig.QQ_CONTROL_HOST
api_port: int = QQControlConfig.QQ_CONTROL_PORT
api_token: str = 'Bearer ' + QQControlConfig.QQ_CONTROL_TOKEN


# 获取驱动器和超级用户配置
driver = get_driver()

# 通过HTTP API发送私聊消息的函数
def send_private_msg_via_api(user_id: int, message_id: int) -> bool:
    """通过HTTP API发送私聊消息
    
    Args:
        user_id: 用户QQ号
        message_id: 消息ID
        
    Returns:
        bool: 是否发送成功
    """
    try:
        conn = http.client.HTTPConnection(api_host, api_port)
        headers = {
            'Content-Type': 'application/json',
            'Authorization': api_token
        }
        payload = json.dumps({
            "user_id": user_id,
            "message_id": message_id
        })
        
        conn.request("POST", "/forward_friend_single_msg", payload, headers)
        res = conn.getresponse()
        res_content = res.read().decode()
        logger.info(f"发送私聊消息给用户 {user_id} 的结果: {res_content}")
        return res.status < 300  # 检查HTTP状态码
        
    except Exception as e:
        logger.opt(exception=True).error(f"发送私聊消息给用户 {user_id} 时出错: {e}")
        return False
    finally:
        if 'conn' in locals():
            conn.close()

# 注册命令
group_pull_cmd = on_command(
    "分组发送",
    priority=5,
    block=True
)


@group_pull_cmd.handle()
async def handle_group_send_command(
    bot: Bot,
    event: MessageEvent,
    args: Message = CommandArg()
):
    # 检查权限，只有超级用户才能使用此命令
    if str(event.user_id) not in driver.config.superusers:
        await group_pull_cmd.finish("您没有权限使用此命令")
    
    # 解析参数
    raw_args = args.extract_plain_text().strip()
    args_parts = raw_args.split(' ', 1)  # 只分割一次
    
    # 如果没有参数，显示使用帮助
    if not raw_args:
        await group_pull_cmd.finish(
            "分组发送插件使用说明：\n"
            "用法：\n"
            "1. 引用需要发送的信息（同bs插件）  分组发送 分组名 \n"
            "请先引用要发送的消息（支持文本、图片等），然后使用此命令转发给指定分组的所有成员。"
        )
    
    # 第一个参数是分组名
    group_name = args_parts[0]
    
    # 获取分组详情
    detail = await _get_group_detail(group_name)
    if not detail:
        await group_pull_cmd.finish(f"未找到分组 {group_name}")
    
    members = detail["members"]
    if not members:
        await group_pull_cmd.finish(f"分组 {group_name} 中没有成员")
    
    # 检查是否有引用回复的消息
    message_id = None
    if event.reply:
        message_id = event.reply.message_id
    elif len(args_parts) >= 2:
        # 如果有第二个参数，则尝试作为消息内容发送（仅支持文本）
        await group_pull_cmd.finish("请通过回复消息的方式来发送图片或其他富媒体内容")
    else:
        await group_pull_cmd.finish("请通过回复消息的方式来发送图片或其他富媒体内容")
    
    # 向所有成员发送消息
    success_count = 0
    fail_count = 0
    
    for member in members:
        qq_id = member["qq_id"]
        try:
            # 使用HTTP API发送消息
            if send_private_msg_via_api(qq_id, message_id):
                success_count += 1
            else:
                fail_count += 1
        except Exception as e:
            fail_count += 1
            # 记录失败但不中断流程
    
    await group_pull_cmd.finish(f"消息发送完成！成功: {success_count}, 失败: {fail_count}")
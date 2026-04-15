from nonebot import (
    on_command,
    logger,
    get_plugin_config
)
from nonebot.adapters.onebot.v11 import (
    GROUP,
    GroupMessageEvent,
    Message,
    Bot
)
from nonebot.plugin import PluginMetadata
from nonebot.params import CommandArg

import json
import http.client
from typing import List, Dict, Any, Optional
from dataclasses import dataclass

from .config import Config
from ...common import JsonUtils
from ...config import QQControlConfig
from src.common.model.model import PluginGroupEnum, PluginBadgeColor

# 加载插件配置
config = get_plugin_config(Config)

api_host: str = QQControlConfig.QQ_CONTROL_HOST
api_port: int = QQControlConfig.QQ_CONTROL_PORT
api_token: str = 'Bearer ' + QQControlConfig.QQ_CONTROL_TOKEN

# 插件元数据
__plugin_meta__ = PluginMetadata(
    name="搬史小助手",
    description="用于在多个群组间转发消息的插件，支持配置可发送和可接收的群组",
    usage="搬史 —— 转发引用的消息到所有可接收群组\n搬史 list —— 查看转发群组列表\n搬史 addpost <群号> —— 添加可发送群组\n搬史 addreceive <群号> —— 添加可接收群组\n搬史 rmpost <群号> —— 移除可发送群组\n搬史 rmreceive <群号> —— 移除可接收群组\n搬史 count —— 查看使用次数统计",
    config=Config,
    supported_adapters={"~onebot.v11"},
    extra={
        "group": PluginGroupEnum.UTILITY.value,
        "badge_color": PluginBadgeColor.GREEN.value
    }
)

# 命令处理器
transport_manual = on_command(
    "搬史",
    aliases={"搬屎", "转发", "banshi", "bs"},
    priority=config.bs_priority,
    block=config.bs_block
)

@dataclass
class GroupInfo:
    """群组信息数据类"""
    group_id: int
    group_name: str

class TransportService:
    """消息转发服务类，封装转发相关的核心逻辑"""
    
    @staticmethod
    def ensure_data_initialized():
        """确保数据结构已初始化"""
        JsonUtils.read(config.bs_data_filename, {
            config.post_groups: [],
            config.receive_groups: [],
            config.banshi_frequency_statistics: {},
            config.postshi_frequency_statistics: {}
        })
    

    
    @staticmethod
    def get_post_groups() -> List[Dict[str, Any]]:
        """获取可以发送bs命令的群列表"""
        TransportService.ensure_data_initialized()
        content, _ = JsonUtils.read(config.bs_data_filename, {config.post_groups: []})
        return content.get(config.post_groups, [])
    
    @staticmethod
    def get_receive_groups() -> List[Dict[str, Any]]:
        """获取可以接收转发的群列表"""
        TransportService.ensure_data_initialized()
        content, _ = JsonUtils.read(config.bs_data_filename, {config.receive_groups: []})
        return content.get(config.receive_groups, [])
    
    @staticmethod
    def update_frequency_statistics(
        transmit_shit_user_id: str,
        transmit_shit_nickname: str,
        post_shit_user_id: str,
        post_shit_nickname: str
    ):
        """搬史插件使用频率统计更新"""
        TransportService.ensure_data_initialized()
        data, _ = JsonUtils.read(config.bs_data_filename, {
            config.post_groups: [],
            config.receive_groups: [],
            config.banshi_frequency_statistics: {},
            config.postshi_frequency_statistics: {}
        })

        transmit_freq: Dict[str, Any] = data.get(config.banshi_frequency_statistics, {})
        transmit_user_stats = transmit_freq.get(transmit_shit_user_id, {"count": 0})
        transmit_freq[transmit_shit_user_id] = {
            "count": transmit_user_stats.get("count", 0) + 1,
            "nickname": transmit_shit_nickname
        }

        post_freq: Dict[str, Any] = data.get(config.postshi_frequency_statistics, {})
        post_user_stats = post_freq.get(post_shit_user_id, {"count": 0})
        post_freq[post_shit_user_id] = {
            "count": post_user_stats.get("count", 0) + 1,
            "nickname": post_shit_nickname
        }

        JsonUtils.update(config.bs_data_filename, {
            config.banshi_frequency_statistics: transmit_freq,
            config.postshi_frequency_statistics: post_freq
        })
    
    @staticmethod
    def forward_group_single_msg(group_id: int, message_id: int) -> bool:
        """转发消息到指定群组
        
        Args:
            group_id: 目标群组ID
            message_id: 要转发的消息ID
            
        Returns:
            bool: 是否转发成功
        """
        try:
            conn = http.client.HTTPConnection(api_host, api_port)
            headers = {
                'Content-Type': 'application/json',
                'Authorization': api_token
            }
            payload = json.dumps({
                "group_id": group_id,
                "message_id": message_id
            })
            
            conn.request("POST", "/forward_group_single_msg", payload, headers)
            res = conn.getresponse()
            res_content = res.read().decode()
            logger.info(f"转发消息到群 {group_id} 的结果: {res_content}")
            return res.status < 300  # 检查HTTP状态码
            
        except Exception as e:
            logger.opt(exception=True).error(f"转发消息到群 {group_id} 时出错: {e}")
            return False
        finally:
            if 'conn' in locals():
                conn.close()
    

    
    @staticmethod
    async def add_post_group(bot: Bot, group_id: int) -> Optional[str]:
        """添加可以发送bs命令的群组
        
        Args:
            bot: Bot实例
            group_id: 要添加的群组ID
            
        Returns:
            Optional[str]: 错误信息，如果成功则为None
        """
        # 检查bot是否已加入该群组
        exists_groups_list = await bot.call_api("get_group_list")
        group_info = next((group for group in exists_groups_list if group["group_id"] == group_id), None)
        
        if not group_info:
            return f"bot 还未加入群组 {group_id} 中"
        
        # 检查是否已在post列表中
        post_groups = TransportService.get_post_groups()
        if any(group["group_id"] == group_id for group in post_groups):
            return f"群 {group_id} 已经在可发送列表中"
        
        # 添加到post列表
        post_groups.append(group_info)
        JsonUtils.update(config.bs_data_filename, {config.post_groups: post_groups})
        return None
    
    @staticmethod
    def remove_post_group(group_id: int) -> Optional[str]:
        """移除可以发送bs命令的群组
        
        Args:
            group_id: 要移除的群组ID
            
        Returns:
            Optional[str]: 错误信息，如果成功则为None
        """
        post_groups = TransportService.get_post_groups()
        
        for i, group in enumerate(post_groups):
            if group["group_id"] == group_id:
                del post_groups[i]
                JsonUtils.update(config.bs_data_filename, {config.post_groups: post_groups})
                return None
        
        return f"群 {group_id} 不在可发送列表中"
    
    @staticmethod
    async def add_receive_group(bot: Bot, group_id: int) -> Optional[str]:
        """添加可以接收转发的群组
        
        Args:
            bot: Bot实例
            group_id: 要添加的群组ID
            
        Returns:
            Optional[str]: 错误信息，如果成功则为None
        """
        # 检查bot是否已加入该群组
        exists_groups_list = await bot.call_api("get_group_list")
        group_info = next((group for group in exists_groups_list if group["group_id"] == group_id), None)
        
        if not group_info:
            return f"bot 还未加入群组 {group_id} 中"
        
        # 检查是否已在receive列表中
        receive_groups = TransportService.get_receive_groups()
        if any(group["group_id"] == group_id for group in receive_groups):
            return f"群 {group_id} 已经在可接收列表中"
        
        # 添加到receive列表
        receive_groups.append(group_info)
        JsonUtils.update(config.bs_data_filename, {config.receive_groups: receive_groups})
        return None
    
    @staticmethod
    def remove_receive_group(group_id: int) -> Optional[str]:
        """移除可以接收转发的群组
        
        Args:
            group_id: 要移除的群组ID
            
        Returns:
            Optional[str]: 错误信息，如果成功则为None
        """
        receive_groups = TransportService.get_receive_groups()
        
        for i, group in enumerate(receive_groups):
            if group["group_id"] == group_id:
                del receive_groups[i]
                JsonUtils.update(config.bs_data_filename, {config.receive_groups: receive_groups})
                return None
        
        return f"群 {group_id} 不在可接收列表中"
    
    @staticmethod
    def get_banshi_frequency_statistics() -> Dict[str, Any]:
        """获取搬史使用频率统计数据"""
        TransportService.ensure_data_initialized()
        data, _ = JsonUtils.read(config.bs_data_filename, {
            config.post_groups: [],
            config.receive_groups: [],
            config.banshi_frequency_statistics: {},
            config.postshi_frequency_statistics: {}
        })
        return data.get(config.banshi_frequency_statistics, {})
    
    @staticmethod
    def get_postshi_frequency_statistics() -> Dict[str, Any]:
        """获取发shi统计"""
        TransportService.ensure_data_initialized()
        data, _ = JsonUtils.read(config.bs_data_filename, {
            config.post_groups: [],
            config.receive_groups: [],
            config.banshi_frequency_statistics: {},
            config.postshi_frequency_statistics: {}
        })
        return data.get(config.postshi_frequency_statistics, {})

async def handle_forward_operation(bot: Bot, event: GroupMessageEvent, message_id: int) -> str:
    """处理消息转发操作
    
    Args:
        bot: Bot实例
        event: 消息事件
        message_id: 要转发的消息ID
        
    Returns:
        str: 操作结果消息
    """
    source_group_id = event.group_id
    
    # 检查当前群组是否在post_groups中
    post_groups = TransportService.get_post_groups()
    is_post_group = any(group["group_id"] == source_group_id for group in post_groups)
    
    # 如果没有配置post_groups，则允许所有群组发送
    if post_groups and not is_post_group:
        logger.warning(f"群组 {source_group_id} 不在可发送列表中")
        return "当前群组没有权限使用搬史功能"
    
    # 获取接收群组列表
    receive_groups = TransportService.get_receive_groups()
    
    if not receive_groups:
        logger.warning(f"空接收群组列表 (用户:{event.user_id} 群组:{event.group_id})")
        return "没有配置可接收的群组"
    
    # 转发消息
    success_cnt = 0
    error_groups = []
    
    for receive_group in receive_groups:
        group_id = receive_group["group_id"]
        # 跳过源群组
        if group_id == source_group_id:
            continue
        
        # 发送消息
        if TransportService.forward_group_single_msg(group_id=group_id, message_id=message_id):
            success_cnt += 1
        else:
            error_groups.append(str(group_id))
    
    # 使用频率统计更新
    TransportService.update_frequency_statistics(
        transmit_shit_user_id=str(event.sender.user_id), 
        transmit_shit_nickname=event.sender.nickname,
        post_shit_user_id=str(event.reply.sender.user_id),
        post_shit_nickname=event.reply.sender.nickname
        
    )
    
    # 构建结果消息
    result_msg = f"已成功转发到 {success_cnt} 个群组"
    if error_groups:
        result_msg += f"\n以下群组发送失败: {', '.join(error_groups)}"
    
    return result_msg

async def handle_list_operation() -> str:
    """处理列出转发群组操作
    
    Returns:
        str: 群组列表消息
    """
    # 获取post群组列表
    post_groups = TransportService.get_post_groups()
    post_groups_str = "\n".join(
        f"群号：{group['group_id']}  群名：{group['group_name']}"
        for group in post_groups
    )
    
    # 获取receive群组列表
    receive_groups = TransportService.get_receive_groups()
    receive_groups_str = "\n".join(
        f"群号：{group['group_id']}  群名：{group['group_name']}"
        for group in receive_groups
    )
    
    result_msg = ""
    result_msg += f"可发送搬史命令的群组 (post_groups):\n"
    result_msg += post_groups_str if post_groups else "无"
    result_msg += "\n\n"
    result_msg += f"可接收转发内容的群组 (receive_groups):\n"
    result_msg += receive_groups_str if receive_groups else "无"
    
    return result_msg

async def handle_list_post_operation() -> str:
    """处理列出可发送群组操作
    
    Returns:
        str: 群组列表消息
    """
    post_groups = TransportService.get_post_groups()
    
    if not post_groups:
        return "没有配置可发送的群组"
    
    group_list = "\n".join(
        f"群号：{group['group_id']}  群名：{group['group_name']}"
        for group in post_groups
    )
    
    return f"可发送搬史命令的群组:\n{group_list}"

async def handle_list_receive_operation() -> str:
    """处理列出可接收群组操作
    
    Returns:
        str: 群组列表消息
    """
    receive_groups = TransportService.get_receive_groups()
    
    if not receive_groups:
        return "没有配置可接收的群组"
    
    group_list = "\n".join(
        f"群号：{group['group_id']}  群名：{group['group_name']}"
        for group in receive_groups
    )
    
    return f"可接收转发内容的群组:\n{group_list}"

async def handle_count_operation(is_show_all: bool) -> str:
    """处理使用次数统计操作
    
    Returns:
        str: 统计结果消息
    """
    banshi_freq = TransportService.get_banshi_frequency_statistics()

    show_cnt = 0
    
    res_msg = "搬史插件使用次数统计(使用bs命令的用户)"
    if not banshi_freq:
        res_msg += "\n无使用记录"
    else:
        # 按使用次数降序排序
        sorted_items = sorted(banshi_freq.items(), key=lambda x: x[1]['count'], reverse=True)
        for _, user_info in sorted_items:
            show_cnt += 1
            if show_cnt > config.bs_max_show_cnt and not is_show_all:
                break
            res_msg += f"\n{user_info['nickname']} 搬史 {user_info['count']} 次"

    show_cnt = 0

    postshi_freq = TransportService.get_postshi_frequency_statistics()
    res_msg += "\n\n发史数据统计(被bs命名转发消息的用户)"
    if not postshi_freq:
        res_msg += "\n无使用记录"
    else:
        # 降序排序
        sorted_items = sorted(postshi_freq.items(), key=lambda x: x[1]['count'], reverse=True)
        for _, user_info in sorted_items:
            show_cnt += 1
            if show_cnt > config.bs_max_show_cnt and not is_show_all:
                break
            res_msg += f"\n{user_info['nickname']} 发史 {user_info['count']} 次"

    return res_msg

@transport_manual.handle()
async def handle_transport(bot: Bot, event: GroupMessageEvent, args: Message = CommandArg()):
    """处理搬史命令的主函数"""
    raw_args = args.extract_plain_text().strip()
    params = raw_args.split() if raw_args else []
    
    try:
        # 无参数模式 - 转发消息
        if not params:
            # 检查是否有引用消息
            if not event.reply:
                await bot.send(event=event, message=config.HELP_MSG)
                return
            
            message_id = event.reply.message_id
            result_msg = await handle_forward_operation(bot, event, message_id)
            await bot.send(event=event, message=result_msg)
            return
        
        # 命令参数模式
        command = params[0].lower()
        
        if command in ["list", "ls", "查看", "查询"]:
            # 查看转发群组列表
            result_msg = await handle_list_operation()
            await bot.send(event=event, message=result_msg)
        elif command in ["listpost", "lspost", "查看发送"]:
            # 查看可发送群组列表
            result_msg = await handle_list_post_operation()
            await bot.send(event=event, message=result_msg)
        elif command in ["listreceive", "lsreceive", "查看接收"]:
            # 查看可接收群组列表
            result_msg = await handle_list_receive_operation()
            await bot.send(event=event, message=result_msg)

        elif command in ["addpost", "添加发送"]:
            # 添加可发送群组
            if len(params) < 2 or not params[1].isdigit():
                await bot.send(event=event, message="请提供合法的群号")
                return
            
            group_id = int(params[1])
            error_msg = await TransportService.add_post_group(bot, group_id)
            
            if error_msg:
                await bot.send(event=event, message=error_msg)
            else:
                await bot.send(event=event, message=f"已将群 {group_id} 添加到可发送列表")

        elif command in ["addreceive", "添加接收"]:
            # 添加可接收群组
            if len(params) < 2 or not params[1].isdigit():
                await bot.send(event=event, message="请提供合法的群号")
                return
            
            group_id = int(params[1])
            error_msg = await TransportService.add_receive_group(bot, group_id)
            
            if error_msg:
                await bot.send(event=event, message=error_msg)
            else:
                await bot.send(event=event, message=f"已将群 {group_id} 添加到可接收列表")

        elif command in ["rmpost", "删除发送", "移除发送"]:
            # 删除可发送群组
            if len(params) < 2 or not params[1].isdigit():
                await bot.send(event=event, message="请提供合法的群号")
                return
            
            group_id = int(params[1])
            error_msg = TransportService.remove_post_group(group_id)
            
            if error_msg:
                await bot.send(event=event, message=error_msg)
            else:
                await bot.send(event=event, message=f"已将群 {group_id} 从可发送列表中移除")

        elif command in ["rmreceive", "删除接收", "移除接收"]:
            # 删除可接收群组
            if len(params) < 2 or not params[1].isdigit():
                await bot.send(event=event, message="请提供合法的群号")
                return
            
            group_id = int(params[1])
            error_msg = TransportService.remove_receive_group(group_id)
            
            if error_msg:
                await bot.send(event=event, message=error_msg)
            else:
                await bot.send(event=event, message=f"已将群 {group_id} 从可接收列表中移除")
                
        elif command in ["count", "计数", "统计"]:
            # 查看使用次数统计
            # 是否列出所有消息
            is_show_all = len(params) >= 2 and params[1] in ["all"]
            result_msg = await handle_count_operation(is_show_all)
            await bot.send(event=event, message=result_msg)

        
    except Exception as e:
        logger.opt(exception=True).error(f"搬史小助手发生错误: {e}")
        await bot.send(event=event, message=f"处理请求时发生错误: {str(e)}")
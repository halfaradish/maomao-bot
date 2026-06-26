from nonebot import on_command, logger, get_plugin_config
from nonebot.adapters.onebot.v11 import GroupMessageEvent, Message
from nonebot.params import CommandArg
from nonebot.plugin import PluginMetadata
import json
import os
from .database import db_manager
from .config import Config
from ...config import DiTingData
from ...common import JsonUtils

# 获取插件配置
config = get_plugin_config(Config)
# 权限检查函数
def check_permission(user_id: str) -> bool:
    """检查用户是否有操作权限"""
    try:
        # 使用JsonUtils读取权限配置文件
        permission_data, _ = JsonUtils.read(
            filename=config.data_filename,
            default={'userid': []}
        )
        
        # 获取允许的用户ID列表
        allowed_users = permission_data.get('userid', [])
        
        # 检查用户ID是否在允许列表中
        return str(user_id) in allowed_users
        
    except Exception as e:
        logger.error(f"权限检查失败: {e}")
        return False



# 默认消息配置
DEFAULT_MSG = (
    "[群统计] 命令使用方法\n"
    "[功能]: 统计群聊信息，支持添加、更新、删除和查看群聊信息\n"
    "[格式]:\n"
    "群统计 add 群号 群名 群功能 - 添加群聊信息\n"
    "群统计 update 群号 群名 群功能 - 更新群聊信息\n"
    "群统计 rm 群号 - 删除指定群聊信息\n"
    "群统计 ls - 查看所有群聊信息\n"
)

# 创建命令处理器
group_statistics_cmd = on_command("群统计", priority=5, block=True)


def format_group_list(groups):
    """格式化群列表输出，每个群信息单独显示，各项各占一行"""
    if not groups:
        return "当前数据库中没有群聊信息"
    
    # 构建标题
    message = f" 群聊信息列表（共{len(groups)}个）\n\n"
    
    # 定义分隔线
    separator = "-" * 30 + "\n"
    
    # 每个群单独显示，各项各占一行
    for i, group in enumerate(groups, 1):
        group_id = group.get('group_id', '未知')
        group_name = group.get('group_name', '未知')
        group_function = group.get('group_function', '未设置')
        
        # 添加群序号和分隔线
        message += f"【{i}】\n"
        
        # 各项信息各占一行，保持对齐
        message += f"群号: {group_id}\n"
        message += f"群名: {group_name}\n"
        message += f"群功能: {group_function}\n"
        
        # 在群之间添加分隔线（最后一个群不需要）
        if i < len(groups):
            message += separator
    

    
    return message


@group_statistics_cmd.handle()
async def handle_group_statistics(event: GroupMessageEvent, args: Message = CommandArg()):
    """处理群统计命令"""
    # 解析参数
    arg_text = args.extract_plain_text().strip()
    if not arg_text:
        await group_statistics_cmd.finish(DEFAULT_MSG)
    
    # 解析命令参数
    parts = arg_text.split()
    
    # 处理子命令
    if len(parts) >= 1 and parts[0] == 'ls':
        # 查看群聊列表
        groups = await db_manager.list_groups()
        message = format_group_list(groups)
        await group_statistics_cmd.finish(message)
    
    elif len(parts) >= 4 and parts[0] == 'add':
        # 权限检查
        if not check_permission(event.user_id):
            await group_statistics_cmd.finish("权限不足，无法执行添加操作")
            
        # 添加群聊信息
        group_id = parts[1]
        # 验证群号格式
        if not group_id.isdigit():
            await group_statistics_cmd.finish("群号格式错误，请输入纯数字")
        
        # 提取群名和群功能（群功能可能包含空格）
        group_name = parts[2]
        group_function = " ".join(parts[3:])
        
        # 执行添加操作
        if await db_manager.add_group(group_id, group_name, group_function):
            await group_statistics_cmd.finish(f"成功添加群聊信息\n群号: {group_id}\n群名: {group_name}\n群功能: {group_function}")
        else:
            # 检查是否是因为群号已存在
            existing_group = await db_manager.get_group_by_id(group_id)
            if existing_group:
                await group_statistics_cmd.finish(f"群聊信息已存在，请使用update命令更新\n群号: {group_id}\n当前群名: {existing_group.get('group_name', '未知')}\n当前群功能: {existing_group.get('group_function', '未设置')}")
            else:
                await group_statistics_cmd.finish("添加群聊信息失败，请检查日志")
    
    elif len(parts) >= 4 and parts[0] == 'update':
        # 权限检查
        if not check_permission(event.user_id):
            await group_statistics_cmd.finish("权限不足，无法执行更新操作")
            
        # 更新群聊信息
        group_id = parts[1]
        # 验证群号格式
        if not group_id.isdigit():
            await group_statistics_cmd.finish("群号格式错误，请输入纯数字")
        
        # 提取群名和群功能（群功能可能包含空格）
        group_name = parts[2]
        group_function = " ".join(parts[3:])
        
        # 执行更新操作
        if await db_manager.update_group(group_id, group_name, group_function):
            await group_statistics_cmd.finish(f"成功更新群聊信息\n群号: {group_id}\n群名: {group_name}\n群功能: {group_function}")
        else:
            await group_statistics_cmd.finish(f"更新失败，未找到群号为 {group_id} 的群聊信息")
    
    elif len(parts) == 2 and parts[0] == 'rm':
        # 权限检查
        if not check_permission(event.user_id):
            await group_statistics_cmd.finish("权限不足，无法执行删除操作")
            
        # 删除群聊信息
        group_id = parts[1]
        # 验证群号格式
        if not group_id.isdigit():
            await group_statistics_cmd.finish("群号格式错误，请输入纯数字")
        
        # 执行删除操作
        if await db_manager.remove_group(group_id):
            await group_statistics_cmd.finish(f"成功删除群聊信息\n群号: {group_id}")
        else:
            await group_statistics_cmd.finish(f"删除失败，未找到群号为 {group_id} 的群聊信息")
    
    elif len(parts) == 1 and parts[0] in ['add', 'rm', 'update']:
        # add、rm和update命令缺少参数
        if parts[0] == 'add':
            await group_statistics_cmd.finish("请提供完整参数，格式：群统计 add 群号 群名 群功能")
        elif parts[0] == 'update':
            await group_statistics_cmd.finish("请提供完整参数，格式：群统计 update 群号 群名 群功能")
        else:
            await group_statistics_cmd.finish("请提供群号，格式：群统计 rm 群号")
    
    else:
        # 参数错误，显示帮助信息
        await group_statistics_cmd.finish(f"命令参数错误\n{DEFAULT_MSG}")

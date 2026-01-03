from nonebot import (
    get_plugin_config,
    get_driver,
    on_command,
    logger,
    Bot
)
from nonebot.plugin import PluginMetadata
from nonebot.adapters.onebot.v11 import (
    GroupMessageEvent,
    Message,
    MessageSegment,
    ActionFailed
)
from nonebot.params import CommandArg

from datetime import datetime
import asyncio

from .config import Config
from ...common import JsonUtils

__plugin_meta__ = PluginMetadata(
    name="mass_kick",
    description="一键退群功能，支持批量将用户从多个群组中踢出，以及管理群组列表",
    usage="一键退群+QQ号\n一键退群 ls\n一键退群 add+群号\n一键退群 rm+群号",
    config=Config,
)

config = get_plugin_config(Config)
driver = get_driver()

# 创建命令处理器
mass_kick_cmd = on_command("一键退群", priority=5, block=True)

def get_managed_groups():
    """获取管理的群组列表"""
    data, _ = JsonUtils.read(
        filename=config.data_filename,
        default={
            "managed_groups": []
        }
    )
    return data.get('managed_groups', [])
async def is_super_admin(user_id: str) -> bool:
    """验证用户是否为超级管理员"""
    # 调试信息：打印超级管理员列表和当前用户ID
    logger.info(f"超级管理员列表: {driver.config.superusers}")
    logger.info(f"当前用户ID: {user_id}")
    result = str(user_id) in driver.config.superusers
    logger.info(f"权限验证结果: {result}")
    return result

async def get_group_member_role(bot: Bot, group_id: str, user_id: str) -> str:
    """获取群成员角色
    返回值: 'owner' - 群主, 'admin' - 管理员, 'member' - 普通成员, None - 不在群中
    """
    try:
        member_info = await bot.get_group_member_info(
            group_id=int(group_id),
            user_id=int(user_id)
        )
        if member_info:
            role = member_info.get('role', 'member')
            # OneBot v11 角色定义: owner, admin, member
            return role
    except ActionFailed:
        # 用户不在群组中或获取信息失败
        return None
    except Exception as e:
        logger.error(f"获取群成员角色失败: 群组{group_id}, 用户{user_id}, 错误: {e}")
        return None
    
    return None

async def check_kick_permission(bot: Bot, group_id: str, operator_id: str, target_user_id: str) -> tuple:
    """检查踢人权限
    返回值: (是否允许, 权限不足原因)
    规则:
    1. 管理员不能踢出管理员和群主
    2. 普通群员不能踢出管理员和群主
    3. 群主可以踢出任何人
    4. 机器人自身也需要符合以上规则
    """
    # 检查操作者权限
    operator_role = await get_group_member_role(bot, group_id, operator_id)
    if operator_role is None:
        return False, "操作者不在群组中"
    
    # 检查目标用户权限
    target_role = await get_group_member_role(bot, group_id, target_user_id)
    if target_role is None:
        return False, "目标用户不在群组中"
    
    # 检查机器人权限
    bot_role = await get_group_member_role(bot, group_id, bot.self_id)
    if bot_role is None:
        return False, "机器人不在群组中"
    
    # 先检查命令者权限
    # 群主可以踢任何人
    if operator_role == "owner":
        pass  # 群主有最高权限
    # 管理员不能踢出管理员和群主
    elif operator_role == "admin":
        if target_role in ["admin", "owner"]:
            return False, "命令者权限不足"
    # 普通群员不能踢出任何人
    elif operator_role == "member":
        return False, "命令者权限不足"
    
    # 再检查机器人权限
    # 机器人作为群主可以踢任何人
    if bot_role == "owner":
        pass  # 机器人是群主，有最高权限
    # 机器人作为管理员不能踢出管理员和群主
    elif bot_role == "admin":
        if target_role in ["admin", "owner"]:
            return False, "机器人权限不足"
    # 机器人作为普通成员不能踢出任何人
    elif bot_role == "member":
        return False, "机器人权限不足"
    
    return True, "权限验证通过"

async def kick_user_from_group(bot: Bot, group_id: str, user_id: str) -> bool:
    """从指定群组踢出用户"""
    try:
        await bot.set_group_kick(
            group_id=int(group_id),
            user_id=int(user_id)
        )
        return True
    except ActionFailed as e:
        logger.warning(f"踢出用户失败: 群组{group_id}, 用户{user_id}, 错误: {e}")
        return False
    except Exception as e:
        logger.error(f"踢出用户异常: 群组{group_id}, 用户{user_id}, 错误: {e}")
        return False

async def log_operation(bot: Bot, operator_id: str, target_user_id: str, 
                       success_groups: list, failed_groups: list):
    """记录操作日志"""
    if not config.log_group_ids:
        return
    
    try:
        log_messages = []
        log_messages.append("=== 一键退群操作日志 ===")
        log_messages.append(f"操作时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        log_messages.append(f"操作者: {operator_id}")
        log_messages.append(f"目标用户: {target_user_id}")
        log_messages.append(f"成功踢出的群组: {len(success_groups)}个")
        
        if success_groups:
            log_messages.append("成功群组列表:")
            for group_id in success_groups:
                log_messages.append(f"  - {group_id}")
        
        if failed_groups:
            log_messages.append(f"踢出失败的群组: {len(failed_groups)}个")
            log_messages.append("失败群组列表:")
            for group_id in failed_groups:
                log_messages.append(f"  - {group_id}")
        
        # 发送到所有日志群组
        log_content = "\n".join(log_messages)
        for log_group_id in config.log_group_ids:
            try:
                await bot.send_group_msg(
                    group_id=int(log_group_id),
                    message=log_content
                )
                logger.info(f"操作日志已发送到群组 {log_group_id}")
            except Exception as e:
                logger.error(f"发送日志到群组 {log_group_id} 失败: {e}")
        
    except Exception as e:
        logger.error(f"记录操作日志失败: {e}")

@mass_kick_cmd.handle()
async def handle_mass_kick(bot: Bot, event: GroupMessageEvent, args: Message = CommandArg()):
    """处理一键退群命令"""
    
    # 验证权限
    if not await is_super_admin(str(event.user_id)):
        await mass_kick_cmd.finish("您没有权限使用此功能")
    
    # 解析参数
    arg_text = args.extract_plain_text().strip()
    if not arg_text:
        await mass_kick_cmd.finish(config.DEFAULT_MSG)
    
    # 解析命令参数
    parts = arg_text.split()
    
    # 处理子命令
    if len(parts) >= 1 and parts[0] == 'ls':
        # 查看群组列表 - ls命令不需要额外参数
        managed_groups = get_managed_groups()
        if not managed_groups:
            await mass_kick_cmd.finish("当前没有配置管理的群组")
        
        message = "当前管理的群组列表：\n"
        for i, group_id in enumerate(managed_groups, 1):
            message += f"{i}. {group_id}\n"
        message += f"\n总计：{len(managed_groups)} 个群组"
        
        await mass_kick_cmd.finish(message)
    
    elif len(parts) >= 2 and parts[0] == 'add':
        # 添加群组 - 支持单个或多个群号
        group_ids = parts[1:]
        
        # 验证所有群号格式
        invalid_ids = [gid for gid in group_ids if not gid.isdigit()]
        if invalid_ids:
            await mass_kick_cmd.finish(f"群号格式错误，以下群号不是纯数字：{', '.join(invalid_ids)}")
        
        # 批量添加
        added_groups = []
        existing_groups = []
        
        for group_id in group_ids:
            if add_managed_group(group_id):
                added_groups.append(group_id)
            else:
                existing_groups.append(group_id)
        
        # 构建结果消息
        result_msg = "批量添加群组完成\n"
        if added_groups:
            result_msg += f"成功添加：{', '.join(added_groups)} ({len(added_groups)}个)\n"
        if existing_groups:
            result_msg += f"已存在：{', '.join(existing_groups)} ({len(existing_groups)}个)"
        
        await mass_kick_cmd.finish(result_msg)
    
    elif len(parts) >= 2 and parts[0] == 'rm':
        # 删除群组 - 支持单个或多个群号
        group_ids = parts[1:]
        
        # 验证所有群号格式
        invalid_ids = [gid for gid in group_ids if not gid.isdigit()]
        if invalid_ids:
            await mass_kick_cmd.finish(f"群号格式错误，以下群号不是纯数字：{', '.join(invalid_ids)}")
        
        # 批量删除
        removed_groups = []
        not_found_groups = []
        
        for group_id in group_ids:
            if remove_managed_group(group_id):
                removed_groups.append(group_id)
            else:
                not_found_groups.append(group_id)
        
        # 构建结果消息
        result_msg = "批量删除群组完成\n"
        if removed_groups:
            result_msg += f"成功删除：{', '.join(removed_groups)} ({len(removed_groups)}个)\n"
        if not_found_groups:
            result_msg += f"不存在：{', '.join(not_found_groups)} ({len(not_found_groups)}个)"
        
        await mass_kick_cmd.finish(result_msg)
    
    elif len(parts) == 1 and parts[0] in ['add', 'rm']:
        # add和rm命令缺少参数
        await mass_kick_cmd.finish(f"请提供群号，格式：一键退群 {parts[0]} 群号1 [群号2 群号3 ...]")
    
    else:
        # 处理原始的一键退群功能
        target_user_id = arg_text
        if not target_user_id.isdigit():
            await mass_kick_cmd.finish("QQ号格式错误，请输入纯数字")
        
        # 获取管理的群组列表
        managed_groups = get_managed_groups()
        if not managed_groups:
            await mass_kick_cmd.finish("当前没有配置管理的群组，请联系管理员配置")
        
        # 检查目标用户是否为自己
        if target_user_id == str(event.user_id):
            await mass_kick_cmd.finish("不能踢出自己")
        
        # 检查目标用户是否为机器人
        if target_user_id == str(bot.self_id):
            await mass_kick_cmd.finish("不能踢出机器人自己")
        
        # 开始处理
        await mass_kick_cmd.send(f"开始处理一键退群，目标用户：{target_user_id}")
        
        # 记录操作日志
        operation_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        operator_id = str(event.user_id)
        
        # 执行批量踢出
        success_groups = []
        failed_groups = []
        
        for group_id in managed_groups:
            try:
                # 检查用户是否在群组中
                try:
                    member_info = await bot.get_group_member_info(
                        group_id=int(group_id), 
                        user_id=int(target_user_id)
                    )
                    if member_info:
                        # 检查踢人权限
                        has_permission, reason = await check_kick_permission(bot, group_id, operator_id, target_user_id)
                        if not has_permission:
                            if reason == "机器人权限不足":
                                logger.warning(f"在群组 {group_id} 中，机器人权限不足，无法踢出用户 {target_user_id}")
                                failed_groups.append(f"{group_id}(机器人权限不足)")
                            elif reason == "命令者权限不足":
                                logger.warning(f"在群组 {group_id} 中，用户 {operator_id} 没有权限踢出用户 {target_user_id}")
                                failed_groups.append(f"{group_id}(命令者权限不足)")
                            else:
                                logger.warning(f"在群组 {group_id} 中，权限检测失败: {reason}")
                                failed_groups.append(f"{group_id}({reason})")
                            continue
                        
                        # 执行踢出操作
                        result = await kick_user_from_group(bot, group_id, target_user_id)
                        if result:
                            success_groups.append(group_id)
                        else:
                            failed_groups.append(group_id)
                    else:
                        failed_groups.append(f"{group_id}(用户不在群中)")
                except ActionFailed:
                    # 用户不在群组中
                    failed_groups.append(f"{group_id}(用户不在群中)")
                
                # 添加操作延迟，避免频率限制
                if config.operation_delay > 0:
                    await asyncio.sleep(config.operation_delay)
                    
            except Exception as e:
                logger.error(f"处理群组 {group_id} 时发生错误: {e}")
                failed_groups.append(f"{group_id}(处理错误)")
        
        # 构建结果消息
        result_msg = f"一键退群操作完成\n"
        result_msg += f"操作时间：{operation_time}\n"
        result_msg += f"操作者：{operator_id}\n"
        result_msg += f"目标用户：{target_user_id}\n"
        result_msg += f"成功踢出的群组：{len(success_groups)} 个\n"
        result_msg += f"失败的群组：{len(failed_groups)} 个\n"
        
        if success_groups:
            result_msg += f"成功群组列表：{', '.join(success_groups)}\n"
        
        if failed_groups:
            result_msg += f"失败群组列表：{', '.join(failed_groups)}"

        # 发送操作日志到所有日志群组
        await log_operation(bot, operator_id, target_user_id, success_groups, failed_groups)

        # 发送结果给操作者
        await mass_kick_cmd.finish(result_msg)


def update_managed_groups(group_ids: list):
    """更新管理的群组列表"""
    data, _ = JsonUtils.read(
        filename=config.data_filename,
        default={
            "managed_groups": [],
            "log_group_ids": config.log_group_ids
        }
    )
    data['managed_groups'] = group_ids
    return JsonUtils.write(config.data_filename, data)


def add_managed_group(group_id: str) -> bool:
    """添加群组到管理列表"""
    managed_groups = get_managed_groups()
    if group_id in managed_groups:
        return False
    managed_groups.append(group_id)
    return update_managed_groups(managed_groups)


def remove_managed_group(group_id: str) -> bool:
    """从管理列表删除群组"""
    managed_groups = get_managed_groups()
    if group_id not in managed_groups:
        return False
    managed_groups.remove(group_id)
    return update_managed_groups(managed_groups)








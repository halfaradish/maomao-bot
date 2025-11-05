"""
Todo提醒插件主入口
注册命令和事件处理器
"""

from nonebot import on_command
from nonebot.adapters.onebot.v11 import Bot, Event, GroupMessageEvent, PrivateMessageEvent
from nonebot.rule import to_me
from nonebot.params import CommandArg
from nonebot.adapters.onebot.v11.message import Message
from nonebot.exception import FinishedException
from nonebot.log import logger
import re
import time
from typing import Optional, Dict, List

from .commands import TodoCommands
# 从 __init__.py 导入已初始化的组件，避免重复初始化
from . import config, db as database, time_parser, scheduler, commands

# 调度器启动状态
scheduler_started = False

# 启动调度器
async def start_scheduler():
    """启动提醒调度器"""
    global scheduler_started
    try:
        await scheduler.start()
        scheduler_started = True
        logger.info("Todo提醒调度器启动成功")
    except Exception as e:
        logger.error(f"Todo提醒调度器启动失败: {e}")
        scheduler_started = False

# 检查调度器状态
def is_scheduler_ready():
    """检查调度器是否已启动"""
    return scheduler_started and scheduler.running

async def create_forward_message(bot: Bot, event: Event, text: str, bot_name: str = "谛听"):
    """发送转发消息格式"""
    def to_node(name: str, uin: str, message: Message):
        """构建统一的格式"""
        return {
            "type": "node",
            "data": {"name": name, "uin": uin, "content": message},
        }
    
    try:
        info = await bot.get_login_info()
        name = info['nickname']
        uin = bot.self_id
        
        # 构建消息节点
        message_nodes = [to_node(name=bot_name, uin=uin, message=Message(text))]
        
        if isinstance(event, GroupMessageEvent):
            await bot.call_api("send_group_forward_msg", group_id=event.group_id, messages=message_nodes)
        else:
            await bot.call_api("send_private_forward_msg", user_id=event.user_id, messages=message_nodes)
    except Exception as e:
        logger.error(f"发送转发消息失败: {e}")
        # 如果转发失败，发送普通消息
        await bot.send(event, text)

def get_todo_help_text():
    """获取todo帮助文本"""
    return """[todo]命令使用详细
[例子]:
/todo ls (列出未完成的todo)
/todo done (列出已完成的todo)
/todo add 时间 内容 (添加个人todo)
/todo 我 时间 内容 (@自己的提醒，如：todo 我 2分钟后 吃饭 或 todo 我 现在 提醒内容)
/todo 群提醒 时间 内容 (群组@全体成员提醒，如：todo 群提醒 现在 提醒内容)
/todo @用户 时间 内容 (创建@指定用户的提醒，如：todo @用户 现在 提醒内容)
/todo 时间 内容 (普通提醒，如：todo 现在 提醒我喝水 或 todo 2分钟后 提醒我休息)
/todo cancel ID (取消todo)
/todo complete ID (完成todo)
/todo delete ID (删除todo)
/todo info ID (查看todo详情)
/todo time (显示支持的时间格式)

时间格式示例：
• 30分钟后 提醒我休息
• 5小时40分 当天会议
• 周一9点 周会
• 每天9点 每日打卡（重复提醒）

使用说明：
• 不指定用户时，默认为个人提醒
• 使用"我"命令会@自己（如：todo 我 2分钟后 吃饭 或 todo 我 现在 提醒内容）
• 使用"现在"、"立刻"、"立即"、"now"作为时间会立即执行提醒（如：todo 现在 提醒我喝水）
• 使用"群提醒"命令会@全体成员（如：todo 群提醒 现在 提醒内容）
• 使用 "@用户 时间 内容" 需要加 todo 前缀，如：todo @某人 现在 提醒内容 或 todo @某人 2分钟后 开会"""

# 使用插件启动钩子
from nonebot import get_driver

@get_driver().on_startup
async def startup():
    """插件启动时初始化"""
    await start_scheduler()

# 主命令注册 - 参考PRD插件格式
todo_cmd = on_command("todo", aliases={"提醒"}, priority=10)


@todo_cmd.handle()
async def handle_todo(bot: Bot, event: Event, args: Message = CommandArg()):
    """处理todo命令 - 参考PRD插件格式"""
    raw_args = args.extract_plain_text().strip()
    params = raw_args.split() if raw_args else []
    
    # 检查是否是@用户提醒（群聊中且消息包含@）
    if isinstance(event, GroupMessageEvent):
        # 检查消息是否包含@用户
        message = event.get_message()
        has_at = any(seg.type == "at" for seg in message)
        if has_at:
            # 这是@用户提醒，需要特殊处理
            try:
                result = await commands.create_user_mention_todo(bot, event, raw_args)
                await todo_cmd.finish(result)
            except FinishedException:
                raise
            except Exception as e:
                logger.error(f"创建@用户提醒失败: {e}")
                await todo_cmd.finish(f"创建@用户提醒失败: {str(e)}")
    
    # 当没有传入参数时，显示帮助信息
    if not params:
        help_text = get_todo_help_text()
        await create_forward_message(bot, event, help_text)
        await todo_cmd.finish()
    
    # 检查调度器是否已启动，如果没有则尝试启动
    if not is_scheduler_ready():
        logger.warning("调度器未启动，尝试启动调度器")
        try:
            await start_scheduler()
            if not is_scheduler_ready():
                logger.error("调度器启动失败，无法处理todo命令")
                await todo_cmd.finish("系统正在初始化，请稍后再试")
                return
        except Exception as e:
            logger.error(f"启动调度器失败: {e}")
            await todo_cmd.finish("系统初始化失败，请稍后再试")
            return
    
    operation = params[0]
    operation_params = params[1:]
    
    try:
        if operation in ["list", "ls"]:
            # 列出未完成的todo
            result = await commands.list_my_todos(bot, event)
            # 使用转发消息格式
            await create_forward_message(bot, event, result)
            await todo_cmd.finish()
        elif operation in ["done", "completed"]:
            # 列出已完成的todo
            result = await commands.list_completed_todos(bot, event)
            # 使用转发消息格式
            await create_forward_message(bot, event, result)
            await todo_cmd.finish()
        elif operation in ["add"]:
            # 添加todo
            if len(operation_params) < 2:
                await todo_cmd.finish("请提供时间和内容，例如：todo add 明天下午3点 开会")
            # 构造符合解析器期望的格式：todo 时间 内容
            content = f"todo {' '.join(operation_params)}"
            result = await commands.create_todo(bot, event, content)
            await todo_cmd.finish(result)
        elif operation in ["cancel"]:
            # 取消todo
            if not operation_params:
                await todo_cmd.finish("请提供todo ID，例如：todo cancel 123")
            result = await commands.cancel_todo(bot, event, operation_params[0])
            await todo_cmd.finish(result)
        elif operation in ["complete", "finish"]:
            # 完成todo
            if not operation_params:
                await todo_cmd.finish("请提供todo ID，例如：todo complete 123")
            result = await commands.complete_todo(bot, event, operation_params[0])
            await todo_cmd.finish(result)
        elif operation in ["delete", "rm"]:
            # 删除todo
            if not operation_params:
                await todo_cmd.finish("请提供todo ID，例如：todo delete 123")
            result = await commands.delete_todo(bot, event, operation_params[0])
            await todo_cmd.finish(result)
        elif operation in ["info", "detail"]:
            # 查看todo详情
            if not operation_params:
                await todo_cmd.finish("请提供todo ID，例如：todo info 123")
            result = await commands.get_todo_info(bot, event, operation_params[0])
            await todo_cmd.finish(result)
        elif operation in ["help"]:
            # help命令显示帮助信息
            help_text = get_todo_help_text()
            await create_forward_message(bot, event, help_text)
            await todo_cmd.finish()
        elif operation in ["time", "时间格式", "formats"]:
            # 显示时间格式
            result = await commands.show_time_formats(bot, event)
            # 使用转发消息格式
            await create_forward_message(bot, event, result)
            await todo_cmd.finish()
        elif operation in ["群提醒", "group"]:
            # 群组@全体成员提醒
            if len(operation_params) < 2:
                await todo_cmd.finish("请提供时间和内容，例如：todo 群提醒 明天下午3点 开会")
            content = f"todo {' '.join(operation_params)}"
            result = await commands.create_group_at_all_todo(bot, event, content)
            await todo_cmd.finish(result)
        elif operation in ["我", "自己"]:
            # @自己的提醒
            if len(operation_params) < 2:
                await todo_cmd.finish("请提供时间和内容，例如：todo 我 2分钟后 吃饭 或 todo 我 现在 提醒内容")
            content = f"todo {' '.join(operation_params)}"
            result = await commands.create_self_mention_todo(bot, event, content)
            await todo_cmd.finish(result)
        else:
            # 默认行为：创建todo
            content = raw_args
            result = await commands.create_todo(bot, event, content)
            await todo_cmd.finish(result)
    except FinishedException:
        # 让 FinishedException 正常传递，不记录为错误
        raise
    except Exception as e:
        logger.error(f"处理todo命令时发生错误: {e}")
        logger.error(f"错误类型: {type(e).__name__}")
        logger.error(f"错误详情: {str(e)}")
        import traceback
        logger.error(f"错误堆栈: {traceback.format_exc()}")
        await todo_cmd.finish(f"处理命令时发生错误: {str(e)}")


# 清除缓存命令
clear_cache_matcher = on_command("清除缓存", priority=1)

@clear_cache_matcher.handle()
async def handle_clear_cache(bot: Bot, event: Event):
    """清除群成员缓存"""
    if isinstance(event, GroupMessageEvent):
        group_id = event.group_id
        # 由于删除了@用户提醒功能，这个命令现在没有实际作用
        await bot.send(event, f"群组 {group_id} 的缓存清除功能已禁用（@用户提醒功能已删除）")
    else:
        await bot.send(event, "此命令只能在群聊中使用")





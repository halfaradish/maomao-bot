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
from src.common.permission import (
    blacklist_guard,
    check_permission,
    ensure_perm_group,
    permission_checker,
)
from src.common.plugin_guard import plugin_enabled
from src.common.send_forward_msg import send_forward_msg
import re
import time
from typing import Optional, Dict, List

# 检查插件开关
_todo_cmd_enabled = plugin_enabled("TODO_CMD_ENABLE")

from .commands import TodoCommands
# 从 __init__.py 导入已初始化的组件，避免重复初始化
from . import config, db as database, time_parser, scheduler, commands

# 调度器启动状态
scheduler_started = False

# 启动调度器
async def start_scheduler():
    """确保提醒任务已注册（幂等；起停由 apscheduler 插件接管）"""
    global scheduler_started
    try:
        scheduler.register_job()
        scheduler_started = True
        logger.info("Todo提醒调度器启动成功")
    except Exception as e:
        logger.error(f"Todo提醒调度器启动失败: {e}")
        scheduler_started = False

# 检查调度器状态
def is_scheduler_ready():
    """检查提醒任务是否已注册"""
    return scheduler_started and scheduler.is_running()

async def create_forward_message(bot: Bot, event: Event, text: str, bot_name: str = "谛听"):
    """发送转发消息格式（节点构造与发送委托 common；失败降级为普通消息）"""
    try:
        await send_forward_msg.by_onebot_api(bot, event, [text], name=bot_name)
    except Exception as e:
        logger.error(f"发送转发消息失败: {e}")
        # 如果转发失败，发送普通消息
        await bot.send(event, text)

def get_todo_help_text():
    """获取todo帮助文本"""
    return """[todo] 命令简表
— 创建提醒 —
/todo 时间 内容                 (默认个人)
/todo add 时间 内容             (个人)
/todo 我 时间 内容              (@自己)
/todo @用户 时间 内容           (@指定用户)
/todo 群提醒 时间 内容          (@全体成员)

— 查询/管理 —
/todo ls                        (未完成列表)
/todo done                      (已完成列表)
/todo info ID                   (详情)
/todo cancel ID                 (取消)
/todo complete ID               (标记完成)
/todo delete ID                 (删除)

提示：
- 未写用户时默认个人提醒；“我”= @自己；“群提醒”= @全体。
- 立刻/现在/立即/now 会立即提醒。
- 支持提前提醒：/todo 时间 -30min 内容"""

# 使用插件启动钩子
from nonebot import get_driver

@get_driver().on_startup
async def startup():
    """插件启动时初始化"""
    if not _todo_cmd_enabled:
        return
    await start_scheduler()


@get_driver().on_startup
async def _ensure_default_perm_groups():
    """确保本插件的默认权限组存在（幂等，不动已有成员）

    拆成两组：普通用户可创建个人提醒，但 @全体 群提醒会打扰整个群，单独一组授予。
    ``todo_reminder:clear_cache`` 是调试命令，不随任何组授予，只留给管理员。
    """
    if not _todo_cmd_enabled:
        return
    await ensure_perm_group(
        "todo_reminder_users",
        "创建提醒",
        ["todo_reminder:use"],
        description="自动创建：创建/取消/完成/删除个人提醒的权限",
    )
    await ensure_perm_group(
        "todo_reminder_managers",
        "群提醒 @全体",
        ["todo_reminder:group_at_all"],
        description="自动创建：创建 @全体成员 群提醒的权限",
    )


#: 只读子命令：仅受黑名单约束，不受权限点约束
READ_ONLY_OPS = {"list", "ls", "done", "completed", "info", "detail", "help"}

# 主命令注册 - 参考PRD插件格式
# 只有在开关开启时才注册命令
if _todo_cmd_enabled:
    # 黑名单模式：普通成员照常可用，只有被拉黑的人用不了
    todo_cmd = on_command("todo", priority=10, permission=blacklist_guard())
else:
    # 创建一个空的命令对象，避免后续代码报错
    todo_cmd = None


async def safe_finish(result: str = ""):
    """安全地结束命令，如果result为空则不发送消息"""
    if not todo_cmd:
        return
    if result and result.strip():
        await todo_cmd.finish(result)
    else:
        await todo_cmd.finish()


if todo_cmd:
    @todo_cmd.handle()
    async def handle_todo(bot: Bot, event: Event, args: Message = CommandArg()):
        """处理todo命令 - 参考PRD插件格式"""
        raw_args = args.extract_plain_text().strip()
        params = raw_args.split() if raw_args else []

        # 群聊里带了 @ 就是「@指定用户提醒」，属于写操作
        has_at = isinstance(event, GroupMessageEvent) and any(
            seg.type == "at" for seg in event.get_message()
        )

        # 只读子命令（列表/详情/帮助）与无参数帮助不受权限点约束；
        # 其余都是写操作，需要 todo_reminder:use
        read_only = not has_at and (not params or params[0] in READ_ONLY_OPS)
        if not read_only and not await check_permission(event, "todo_reminder:use"):
            await todo_cmd.finish("您没有权限使用此功能")

        if has_at:
            # @用户提醒需要特殊处理
            try:
                result = await commands.create_user_mention_todo(bot, event, raw_args)
                await safe_finish(result)
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
            except FinishedException:
                # finish() 靠这个异常收尾（它是 Exception 子类）；吞掉会继续往下
                # 处理命令，而调度器恰恰还没就绪
                raise
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
                    await todo_cmd.finish("请提供时间和内容，例如：todo add 30分钟后 开会")
                # 构造符合解析器期望的格式：todo 时间 内容
                content = f"todo {' '.join(operation_params)}"
                result = await commands.create_todo(bot, event, content)
                await safe_finish(result)
            elif operation in ["cancel"]:
                # 取消todo
                if not operation_params:
                    await todo_cmd.finish("请提供todo ID，例如：todo cancel 123")
                result = await commands.cancel_todo(bot, event, operation_params[0])
                await safe_finish(result)
            elif operation in ["complete", "finish"]:
                # 完成todo
                if not operation_params:
                    await todo_cmd.finish("请提供todo ID，例如：todo complete 123")
                result = await commands.complete_todo(bot, event, operation_params[0])
                await safe_finish(result)
            elif operation in ["delete", "rm"]:
                # 删除todo
                if not operation_params:
                    await todo_cmd.finish("请提供todo ID，例如：todo delete 123")
                result = await commands.delete_todo(bot, event, operation_params[0])
                await safe_finish(result)
            elif operation in ["info", "detail"]:
                # 查看todo详情
                if not operation_params:
                    await todo_cmd.finish("请提供todo ID，例如：todo info 123")
                result = await commands.get_todo_info(bot, event, operation_params[0])
                await safe_finish(result)
            elif operation in ["help"]:
                # help命令显示帮助信息
                help_text = get_todo_help_text()
                await create_forward_message(bot, event, help_text)
                await todo_cmd.finish()
            elif operation in ["群提醒", "group"]:
                # 群组@全体成员提醒
                if len(operation_params) < 2:
                    await todo_cmd.finish("请提供时间和内容，例如：todo 群提醒 30分钟后 开会")
                if not await check_permission(event, "todo_reminder:group_at_all"):
                    await todo_cmd.finish("您没有权限使用群提醒（@全体）功能")
                content = f"todo {' '.join(operation_params)}"
                result = await commands.create_group_at_all_todo(bot, event, content)
                await safe_finish(result)
            elif operation in ["我", "自己"]:
                # @自己的提醒
                if len(operation_params) < 2:
                    await todo_cmd.finish("请提供时间和内容，例如：todo 我 2分钟后 吃饭 或 todo 我 现在 提醒内容")
                content = f"todo {' '.join(operation_params)}"
                result = await commands.create_self_mention_todo(bot, event, content)
                await safe_finish(result)
            else:
                # 默认行为：创建todo
                # 构造符合解析器期望的格式：todo 时间 内容
                content = f"todo {raw_args}"
                result = await commands.create_todo(bot, event, content)
                await safe_finish(result)
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


# 清除缓存命令（调试用，仅管理员与授权者；handler 无实际业务）
clear_cache_matcher = on_command(
    "清除缓存", priority=1,
    permission=permission_checker("todo_reminder:clear_cache"),
)

@clear_cache_matcher.handle()
async def handle_clear_cache(bot: Bot, event: Event):
    """清除群成员缓存"""
    if isinstance(event, GroupMessageEvent):
        group_id = event.group_id
        # 由于删除了@用户提醒功能，这个命令现在没有实际作用
        await bot.send(event, f"群组 {group_id} 的缓存清除功能已禁用（@用户提醒功能已删除）")
    else:
        await bot.send(event, "此命令只能在群聊中使用")





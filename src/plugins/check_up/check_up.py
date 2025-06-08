import nonebot
from nonebot import Bot, on_command
from nonebot.plugin import PluginMetadata
from nonebot.adapters.onebot.v11 import MessageEvent, GroupMessageEvent, PrivateMessageEvent
from nonebot.adapters import Message
from nonebot.params import CommandArg
from datetime import datetime
from nonebot import require
from nonebot import get_bot
require("nonebot_plugin_apscheduler")
from nonebot_plugin_apscheduler import scheduler
from nonebot import logger
from nonebot import get_driver

from ...common import get_working_time
from .config import Config

global_config = get_driver().config
plugin_config = Config.parse_obj(global_config.dict())

__plugin_meta__ = PluginMetadata(
    name="check_up",
    description="考勤相关插件, 支持手动输入日期查看考勤情况, 同时会每日推送考勤情况",
    usage="",
    config=Config,
    supported_adapters={ "~onebot.v11" }
)

check_up_command = on_command(
    "考勤",
    aliases={"考勤状况", "今日考勤", "check"},
    priority=plugin_config.priority,
    block=plugin_config.block
)

@check_up_command.handle()
async def check_up(bot: Bot, event: MessageEvent, args: Message = CommandArg()):
    try:
        # 初始化参数变量
        date_val = None # 目标类型：datetime 或 None
        range_val = 1 # 目标类型：int 或 None

        # 提取原始参数并分割（参数用空格分隔）
        raw_args = args.extract_plain_text().strip()
        params = raw_args.split() if raw_args else []

        if not params:
            await bot.send(event=event, message=plugin_config.DEFAULT_MSG)
            return

        # 校验参数数量
        if len(params) > 2:
            await bot.send(event=event, message="参数过多！最多支持 2 个参数(date 和 range)")
            return
        # 处理 date 参数（字符串转 datetime）
        if len(params) >= 1:
            date_str = params[0]
            try:
                # 尝试按指定格式解析日期（如 YYYY-MM-DD）
                date_val = datetime.strptime(date_str, "%Y-%m-%d")
            except ValueError:
                await bot.send(event=event, message=f"日期格式错误! 请确保数据合法, 并使用了 YYYY-MM-DD 格式(当前: {date_str})")
                return
        # 处理 range 参数（字符串转 int）
        if len(params) == 2:
            range_str = params[1]
            if not range_str.isdigit():
                await bot.send(event=event, message=f"请确保 range 参数 '{range_str}' 为合法的正整数")
                return
            range_val = int(range_str)  # 手动转为 int
        
        result_msg = get_working_time(date_val, range_val)
        await bot.send(event=event, message=result_msg)
        
    except Exception as e:
        logger.opt(exception=True).warning("[考勤]响应错误")
        await bot.send(event=event, message=f"响应失败:\n{e}")



@scheduler.scheduled_job("cron", hour=plugin_config.TIMING_HOUR, minute=plugin_config.TIMING_MINUTE ,second=plugin_config.TIMING_SECOND)
async def daily_timing():
    """每天指定时间向指定群发送消息"""
    bot = get_bot()

    msg = get_working_time()
    group_ids = plugin_config.GROUP_IDS

    for group_id in group_ids:
        try:
            payload = {
                "group_id": str(group_id),
                "message": [
                    {
                        "type": "text",
                        "data": {
                            "text": msg
                        }
                    }
                ]
            }
            await bot.call_api("send_group_msg", **payload)
        except Exception as e:
            logger.opt(exception=True).warning(f"发送消息到群 {group_id} 失败") 

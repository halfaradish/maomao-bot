from nonebot import Bot, on_command, require, get_driver, get_bot, logger, get_plugin_config
from nonebot.plugin import PluginMetadata
from nonebot.adapters.onebot.v11 import MessageEvent
from nonebot.adapters import Message
from nonebot.params import CommandArg
require("nonebot_plugin_apscheduler")
from nonebot_plugin_apscheduler import scheduler
from datetime import datetime

from .working_time import get_working_time
from .config import Config

plugin_config = get_plugin_config(Config)

__plugin_meta__ = PluginMetadata(
    name="check_up",
    description="考勤相关插件, 支持手动输入日期查看考勤情况, 同时会每日推送考勤情况",
    usage="",
    config=Config,
    supported_adapters={ "~onebot.v11" }
)

check_up_command = on_command(
    "考勤",
    aliases={"考勤状况", "check"},
    priority=plugin_config.priority,
    block=plugin_config.block
)

async def is_date_datetime(bot: Bot, event: MessageEvent, date_str: str):
    """判断date参数是否合法, 如果不合法之间返回错误消息"""
    try:
        date_val = datetime.strptime(date_str, "%Y-%m-%d")
        return date_val
    except ValueError:
        await bot.send(event=event, message=f"日期格式错误! 请确保数据合法, 并使用了 YYYY-MM-DD 格式(当前: {date_str})")
        return None

async def is_range_num(bot: Bot, evnet: MessageEvent, range_str: str):
    """判断range参数是否合法, 如果不合法直接返回错误消息"""
    if not range_str.isdigit():
        await bot.send(event=evnet, message=f"请确保 range 参数 '{range_str}' 为合法的正整数")
        return None
    return int(range_str)

@check_up_command.handle()
async def check_up(bot: Bot, event: MessageEvent, args: Message = CommandArg()):
    try:
        # 初始化参数变量
        date_val: datetime = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)
        range_val: int = 1

        # 提取原始参数并分割（参数用空格分隔）
        raw_args = args.extract_plain_text().strip()
        params = raw_args.split() if raw_args else []

        # 没有参数时 发送默认消息
        if not params:
            await bot.send(event=event, message=plugin_config.DEFAULT_MSG)
            return

        # 校验参数数量
        if len(params) > 2:
            await bot.send(event=event, message="参数过多！最多支持 2 个参数(date 和 range)")
            return
        
        # 恰有两个变量时
        if len(params) == 2:
            # 验证第一个参数
            date_str = params[0]
            date_val = await is_date_datetime(bot=bot, event=event, date_str=date_str)
            if date_val is None:
                return
            # 验证第二个参数
            range_str = params[1]
            range_val = await is_range_num(bot=bot, evnet=event, range_str=range_str)
            if range_val is None:
                return
        # 恰有一个参数时
        elif len(params) == 1:
            range_str = params[0]
            range_val = await is_range_num(bot=bot, evnet=event, range_str=range_str)
            if range_val is None:
                return
        # region 旧处理逻辑
        # # 处理 date 参数（字符串转 datetime）
        # if len(params) >= 1:
        #     date_str = params[0]
        #     try:
        #         # 尝试按指定格式解析日期（如 YYYY-MM-DD）
        #         date_val = datetime.strptime(date_str, "%Y-%m-%d")
        #     except ValueError:
        #         await bot.send(event=event, message=f"日期格式错误! 请确保数据合法, 并使用了 YYYY-MM-DD 格式(当前: {date_str})")
        #         return
        # # 处理 range 参数（字符串转 int）
        # if len(params) == 2:
        #     range_str = params[1]
        #     if not range_str.isdigit():
        #         await bot.send(event=event, message=f"请确保 range 参数 '{range_str}' 为合法的正整数")
        #         return
        #     range_val = int(range_str)  # 手动转为 int
        # endregion

        result_msg = get_working_time(date=date_val, range=range_val)
        await bot.send(event=event, message=result_msg)
    except Exception as e:
        logger.opt(exception=True).warning("[考勤]响应错误")

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

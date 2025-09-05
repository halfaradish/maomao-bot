from nonebot import get_plugin_config, logger, on_command, require, get_bot
from nonebot.plugin import PluginMetadata
from nonebot.params import CommandArg
from nonebot.adapters.onebot.v11 import(
    Bot,
    Message,
    PrivateMessageEvent,
    GroupMessageEvent,
    MessageSegment
)
require("nonebot_plugin_apscheduler")
from nonebot_plugin_apscheduler import scheduler

from datetime import datetime
from typing import Union

from ...common import JsonUtils, BuildUri
from .config import Config
from .sub_condition import Submission

__plugin_meta__ = PluginMetadata(
    name="sub_records",
    description="",
    usage="",
    config=Config,
)

config = get_plugin_config(Config)

cf_sub_command = on_command(
    "过题^",
    priority=config.priority,
    block=config.block
)

@scheduler.scheduled_job("cron", day_of_week=0, hour=10, minute=00, id="send_submissions_msg")
async def _():
    """每周发送过题记录"""
    bot = get_bot()
    submission = Submission()

    data, _ = JsonUtils.read('sub_records.json', {
        "submission_groups": []
    })
    group_ids = data["submission_groups"]

    success, pic_path = submission.create_ranking_table(upstream_days=7)
    if not success and pic_path:
        for group_id in group_ids:
            await bot.send_group_msg(
                group_id=group_id,
                message=config.scheduled_default_msg
            )
    elif success and pic_path:
        pic_uri = BuildUri.create_napcat_file_uri(file_path=pic_path)
        pic_msg = MessageSegment.image(pic_uri)
        for group_id in group_ids:
            await bot.send_group_msg(
                group_id=group_id,
                message=pic_msg
            )

@cf_sub_command.handle()
async def _(bot: Bot, event: Union[GroupMessageEvent, PrivateMessageEvent], args: Message = CommandArg()):
    try:
        # 提取原始参数并分割（参数用空格分隔）
        raw_args = args.extract_plain_text().strip()
        params: list[str] = raw_args.split() if raw_args else []

        # 没有参数时 发送默认消息
        if not params:
            await cf_sub_command.finish("[过题]命令使用方法\n[参数]\n范围(int): 展示从上一日开始，上溯x天的cf过题数据")
        
        # # 权限检测
        # group_whitelist, person_whitelist = get_whitelist()
        # if str(event.group_id) not in group_whitelist and str(event.user_id) not in person_whitelist and str(event.user_id) not in superuser:
        #     logger.warning(f"用户 {event.user_id} 尝试使用 '过题' 功能，但没有权限")
        #     await cf_sub_command.finish(f"你没有权限使用 '过题' 功能")

        if not params[0].isdigit():
            await cf_sub_command.finish("参数错误")

        submission = Submission()
        success, pic_path = submission.create_ranking_table(upstream_days=int(params[0]))
        logger.info(pic_path)
        if not success and pic_path:
            await cf_sub_command.finish(pic_path)
        elif success and pic_path:
            pic_uri = BuildUri.create_napcat_file_uri(file_path=pic_path)
            pic_msg = MessageSegment.image(pic_uri)
            await cf_sub_command.finish(pic_msg)
    except Exception as e:
        logger.opt(exception=True).warning(f"[过题]响应错误: {e}")

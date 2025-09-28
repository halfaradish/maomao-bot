from nonebot import get_plugin_config, logger, on_command, require, get_bot
from nonebot.plugin import PluginMetadata
from nonebot.params import CommandArg
from nonebot.exception import FinishedException
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
    aliases={"过题"},
    priority=config.priority,
    block=config.block
)

def is_valid_gap_time(upstream_days):
    """
    判断过题天数是否合理

    params:

    upstream_days: 上溯的天数
    
    return:
    
    is_valid_num: 上溯的天数是否合法
    msg: 错误信息
    """
    end_time: datetime = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)
    min_time: datetime = datetime(1, 1, 1)

    max_x: int = (end_time - min_time).days

    if not isinstance(upstream_days, int):
        return (False, "天数必须是整数")
    if upstream_days < 0:
        return (False, "天数不能为负数")
    if upstream_days > max_x:
        return (False, f"天数参数过大，超出datetime计算范围，最大允许天数为 {max_x} 天（从{end_time.date()}回溯到公元1年1月1日）")
    return (True, None)

@scheduler.scheduled_job("cron", day_of_week=0, hour=10, minute=00, id="send_submissions_msg")
async def _():
    """每周发送过题记录"""
    bot = get_bot()
    submission = Submission()

    data, _ = JsonUtils.read(config.DATA_FILENAME, {
        "submission_groups": []
    })
    group_ids = data["submission_groups"]

    success, pic_path = await submission.create_ranking_table(upstream_days=7)
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

        # 读取需要筛选的数据
        data, _ = JsonUtils.read(
            filename=config.DATA_FILENAME,
            default={
                "roles_name": ["管理员", "现役", "退役", "预备役"],
                "school": ["广西大学", "广西师范大学", "江西农业大学"],
                "person_users": [],
                "group_users": []
            }
        )
        
        # 权限检测
        group_users = data.get('group_users', [])
        person_users = data.get('person_users', [])
        if str(event.group_id) not in group_users and str(event.user_id) not in person_users:
            logger.warning(f"用户 {event.user_id} 尝试使用 '过题' 功能，但没有权限")
            await cf_sub_command.finish("你没有权限使用 '过题' 功能")

        # 模板
        roles_name: list = data.get('roles_name', [])
        schools: list = data.get('school', [])

        # 查询参数
        upstream_days = None
        needed_roles = []
        needed_schools = []
        needed_users = []
        for param in params:
            if param.isdigit():
                # 处理数字
                upstream_days = int(param)
            elif param in roles_name:
                # 处理身份信息
                needed_roles.append(param)
            elif param in schools:
                # 处理学校信息
                needed_schools.append(param)
            else:
                # 处理用户信息
                needed_users.append(param)

        if upstream_days:
            is_valid_num, msg = is_valid_gap_time(upstream_days)
            if not is_valid_num:
                await cf_sub_command.finish(msg)

        # 过滤参数
        query_params = {
            "upstream_days": upstream_days,
            "needed_roles": needed_roles,
            "needed_schools": needed_schools,
            "needed_users": needed_users
        }
        logger.info(query_params)
        filtered_params = {
            key: value for key, value in query_params.items() if value
        }

        # 查询数据库
        submission = Submission()
        success, pic_path = await submission.create_ranking_table(**filtered_params)
        logger.info(pic_path)
        if not success and pic_path:
            await cf_sub_command.finish(pic_path)
        elif success and pic_path:
            pic_uri = BuildUri.create_napcat_file_uri(file_path=pic_path)
            pic_msg = MessageSegment.image(pic_uri)
            await cf_sub_command.finish(pic_msg)
    except FinishedException:
        # 让 FinishedException 正常传递，不记录为错误
        raise
    except Exception as e:
        logger.opt(exception=True).warning(f"[过题]响应错误: {e}")

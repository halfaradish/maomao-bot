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
import platform

# ========= Linux/DLL 适配 =========
# Windows -> 使用 DLL
# Linux   -> 使用 SO
if platform.system() == "Windows":
    LIB_MODE = "DLL 模式运行（Windows）"
else:
    LIB_MODE = "SO 模式运行（Linux）"

logger.info(f"[sub_records] 当前系统加载方式：{LIB_MODE}")

# ========= 导入业务 =========
from ...common import JsonUtils
from .config import Config
from .sub_condition import Submission


__plugin_meta__ = PluginMetadata(
    name="sub_records",
    description="过题统计插件（Linux + Windows 兼容模式）",
    usage="过题 [天数] [学校] [身份] [人名] 可组合筛选",
    config=Config,
)

config = get_plugin_config(Config)


# ======== 指令入口 =========
cf_sub_command = on_command(
    "过题^",
    aliases={"过题"},
    priority=config.sub_record_priority,
    block=config.sub_record_block
)


# ========= 天数验证 =========
def is_valid_gap_time(upstream_days):
    end_time: datetime = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)
    min_time: datetime = datetime(1, 1, 1)
    max_x: int = (end_time - min_time).days

    if not isinstance(upstream_days, int):
        return (False, "天数必须为整数")
    if upstream_days < 0:
        return (False, "天数不能为负数")
    if upstream_days > max_x:
        return (False, f"超出 datetime 范围，最大允许 {max_x} 天")
    return (True, None)


# ========= 每周定时推送 =========
@scheduler.scheduled_job("cron", day_of_week=0, hour=10, minute=00, id="send_submissions_msg")
async def _():
    bot = get_bot()
    submission = Submission()

    data, _ = JsonUtils.read(config.DATA_FILENAME, {"submission_groups": []})
    group_ids = data["submission_groups"]

    success, msg, pic = await submission.create_ranking_table(upstream_days=7)
    if not success:
        for gid in group_ids:
            await bot.send_group_msg(group_id=gid, message=config.scheduled_default_msg)
    elif pic:
        img = MessageSegment.image(pic)
        for gid in group_ids:
            await bot.send_group_msg(group_id=gid, message=img)



# ========= 指令执行 =========
@cf_sub_command.handle()
async def _(bot: Bot, event: Union[GroupMessageEvent, PrivateMessageEvent], args: Message = CommandArg()):
    try:
        raw = args.extract_plain_text().strip()
        params = raw.split() if raw else []

        # 无参数 → 原始风格提示完全保留
        if not params:
            await cf_sub_command.finish(
                "[过题] 使用方法：\n"
                "  过题 7              → 最近7天\n"
                "  过题 7 管理员       → 限角色\n"
                "  过题 7 广西大学     → 限学校\n"
                "  可组合条件，支持身份+学校+用户混查"
            )

        data, _ = JsonUtils.read(config.DATA_FILENAME, {
            "roles_name": ["管理员", "现役", "退役", "预备役"],
            "school": ["广西大学", "广西师范大学", "江西农业大学"],
            "person_users": [],
            "group_users": []
        })

        # 权限验证
        if str(event.group_id) not in data["group_users"] and str(event.user_id) not in data["person_users"]:
            logger.warning(f"权限不足 user={event.user_id}")
            await cf_sub_command.finish("你没有权限使用 '过题' 功能")

        # 解析筛选参数
        roles = data["roles_name"]
        schools = data["school"]

        upstream_days = None
        need_roles = []
        need_schools = []
        need_users = []

        for p in params:
            if p.isdigit(): upstream_days = int(p)
            elif p in roles: need_roles.append(p)
            elif p in schools: need_schools.append(p)
            else: need_users.append(p)

        if upstream_days:
            ok, msg = is_valid_gap_time(upstream_days)
            if not ok: await cf_sub_command.finish(msg)

        query = {
            "upstream_days": upstream_days,
            "needed_roles": need_roles,
            "needed_schools": need_schools,
            "needed_users": need_users
        }
        filtered = {k: v for k, v in query.items() if v}

        submission = Submission()
        success, msg, pic = await submission.create_ranking_table(**filtered)

        if not success: await cf_sub_command.finish(msg)
        if pic: await cf_sub_command.finish(MessageSegment.image(pic))
        await cf_sub_command.finish("图片生成失败，请稍后重试")

    except FinishedException:
        raise
    except Exception as e:
        logger.opt(exception=True).warning(f"[过题]异常: {e}")
        await cf_sub_command.finish("运行出错，日志已记录。")

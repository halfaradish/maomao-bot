from nonebot import(
    get_plugin_config,
    require,
    logger,
    get_bot,
    on_command
)
from nonebot.plugin import PluginMetadata
from nonebot.adapters.onebot.v11 import(
    GroupMessageEvent,
    PrivateMessageEvent,
    Message,
    MessageEvent,
    Bot
)

import uuid
from datetime import datetime, timedelta, date
from nonebot_plugin_apscheduler import scheduler

from ...common import utils, JsonUtils
from .config import Config
from .get_range_sub import DailySubCondition

__plugin_meta__ = PluginMetadata(
    name="shadow_problem_view",
    description="",
    usage="",
    config=Config,
)

require("nonebot_plugin_apscheduler")
config = get_plugin_config(Config)

def is_rookie(ac_time: datetime, enter_time: date) -> bool:
    """判断是否在入队初年"""
    year_diff = ac_time.year - enter_time.year
    return year_diff >= 0 and year_diff <= 1

async def send_record_to_groups(record: dict):
    """将记录发送到指定群聊"""
    problem_url = utils.GenerateProblemUrl.get_problem_url(problem_id=record['problem_id'], platform=record['platform'])
    if not problem_url:
        problem_url = "未知链接"
    try:
        bot: Bot = get_bot()
        # 消息模板
        msg = (
            f"影子过题:\n"
            f"{record['real_name']} 在 {record['ac_time'].year - record['enter_time'].year} 年前的今天 {record['ac_time'].strftime('%Y-%m-%d %H:%M:%S')} 完成了 {record['platform']} 题目 '{record['problem_name']}'\n"
            f"题目链接：{problem_url}\n"
        )
        data, _ = JsonUtils.read(
            filename=config.data_filename,
            default={
                "groups_send_by_plugin": []
            }
        )
        groups: list[str] = data.get('groups_send_by_plugin', [])
        # 发送消息
        for group_id in groups:
            await bot.send_group_msg(
                group_id=group_id,
                message=msg
            )
    except Exception as e:
        logger.error(f"发送消息失败: {e}")

async def schedule_job():
    """
    影子推题

    每天凌晨四点获取数据并存入定时任务
    """
    now: datetime = datetime.now()
    if now.hour >= config.day_start_hour:
        start_datetime: datetime = now.replace(hour=config.day_start_hour, minute=0, second=0)
        end_datetime: datetime = start_datetime + timedelta(days=1)
    else:
        end_datetime: datetime = now.replace(hour=config.day_start_hour, minute=0, second=0)
        start_datetime: datetime = end_datetime - timedelta(days=1)

    logger.debug(f"开始获取数据......")
    records: list[dict] = DailySubCondition.get_daily_sub_records(start_datetime=start_datetime, end_datetime=end_datetime)
    logger.debug(f"获取数据成功: {records}")

    # 安排任务
    logger.info(f"成功获取 {len(records)} 条数据，开始安排任务......")
    sucessed_cnt: int = 0
    for i, record in enumerate(records):
        # 判断入队年份是否正确
        if not is_rookie(ac_time=record['ac_time'], enter_time=record['enter_time']):
            logger.debug(f"该队员:{record['real_name']} 在 {record['enter_time']} 入队，此时:{record['ac_time'].strftime('%Y-%m-%d %H:%M:%S')} 不是入队初期队员")
            continue
        
        # 获取记录中的时分秒
        record_time: datetime = record["ac_time"]
        # 那年今日的记录对应的今日时间
        try:
            scheduled_time = record_time.replace(year=now.year)
        except ValueError:
            # 处理闰年问题，2月29日转换为3月1日
            if record_time.month == 2 and record_time.day == 29:
                scheduled_time = datetime(now.year, 3, 1, record_time.hour, record_time.minute, record_time.second)
            else:
                raise

        # 检查时间是否过期
        if scheduled_time < now:
            logger.debug(f"有一条记录已过时: real_name:{record['real_name']} platform:{record['platform']} pid:{record['problem_id']}-'{record['problem_name']}' ac_time:{record['ac_time'].strftime('%Y-%m-%d %H:%M:%S')}")
            continue

        # 计算距离发送消息还剩多久时间
        time_diff = scheduled_time - now

        job_id = f"shadow_problem_{uuid.uuid4().hex[:8]}"
        
        scheduler.add_job(
            send_record_to_groups,
            'date',
            run_date=scheduled_time,
            args=[record],
            id=job_id
        )
        logger.success(f"已安排一条记录 job_id:{job_id} 在 {scheduled_time.strftime('%Y-%m-%d %H:%M:%S')} 发送，距离现在还有 {time_diff}. 记录详细: real_name:{record['real_name']} platform:{record['platform']} pid:{record['problem_id']}-'{record['problem_name']}' ac_time:{record['ac_time'].strftime('%Y-%m-%d %H:%M:%S')}")
        sucessed_cnt += 1
    logger.success(f"成功安排 {sucessed_cnt} 条数据")

@scheduler.scheduled_job("cron", hour=config.day_start_hour, minute=00, id="shadow_problem_view")
async def _():
    await schedule_job()

@scheduler.scheduled_job("date", run_date=datetime.now() + timedelta(seconds=5), id="initial_shadow_problem_view")
async def _():
    logger.info("[shadow_problem_view]插件首次加载，获取初始数据并发送任务...")
    await schedule_job()
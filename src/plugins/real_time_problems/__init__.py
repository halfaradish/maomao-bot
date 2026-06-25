from nonebot import get_plugin_config, require, logger, on_command, get_bot
from nonebot.params import CommandArg
from nonebot.exception import FinishedException
from nonebot.plugin import PluginMetadata
from nonebot_plugin_apscheduler import scheduler
from nonebot.adapters.onebot.v11 import Message
from nonebot.rule import Rule
# 引入定时任务功能
require("nonebot_plugin_apscheduler")

from datetime import datetime, timedelta
from typing import List, Dict, Any

from .config import Config
# 导入HourSubCondition类
from .get_hour_problems import HourSubCondition
from ...common import utils, JsonUtils
from src.common.model.model import PluginGroupEnum, PluginBadgeColor

# 插件基本信息
__plugin_meta__ = PluginMetadata(
    name="实时过题",
    description="实时过题数据展示插件，每小时自动展示集训队人员的过题情况",
    usage="检查过题 —— 手动查看最近60分钟的过题情况\n检查过题 <分钟数> —— 查看指定分钟数内的过题情况（最大120分钟）",
    config=Config,
    supported_adapters={"~onebot.v11"},
    extra={
        "group": PluginGroupEnum.CONTEST.value,
        "badge_color": PluginBadgeColor.YELLOW.value
    }
)

# 获取插件配置
config = get_plugin_config(Config)
# 自动查询的时间间隔
check_gap_minutes = config.rtp_check_gap_minutes

def is_enable():
    """是否启动实时过题查询"""
    return config.rtp_check_enable
logger.info(f"实时过题命令开关状态：{config.rtp_check_enable}")

# 可以在QQ群里发送"检查过题"来手动查看
check_ac_command = on_command(
    config.rtp_check_cmd,
    aliases={"过题统计"},
    rule=Rule(is_enable),
    priority=config.rtp_check_priority
)

class RealTimeProblemsPlugin:
    """实时过题插件主类"""
    
    def __init__(self):
        pass
    
    def create_message(self, records: List[Dict[str, Any]], minutes = check_gap_minutes) -> Message:
        """
        把过题记录列表转换成QQ消息
        """
        # 如果没有记录，直接返回None（不发送消息）
        if not records:
            return None

        # 创建消息对象
        message = Message(f"[实时过题](前 {minutes} 分钟)\n")
        # 遍历每条记录
        for record in records:
            # 从记录中获取各个字段
            realName = record["realName"]        # 姓名
            platform = record["platform"]          # 平台
            problemName = record["problemName"]  # 题目名称
            acTime = record["acTime"].strftime("%H:%M")  # 过题时间

            # 生成题目链接
            problemLink = utils.GenerateProblemUrl.get_problem_url(platform=platform, problem_id=record['problemId'])

            # 构建单条记录的消息
            record_message = f"{realName} 在 {acTime} 通过了\n"
            record_message += f"{platform} - {problemName}\n"

            # 如果配置了显示难度，并且记录中有难度信息
            if getattr(config, "show_difficulty", True) and "difficulty" in record and record["difficulty"] is not None:
                difficulty_display = record["difficulty"]
                record_message += f"难度: {difficulty_display}\n"
            
            # 加上链接
            if problemLink:
                record_message += f"{problemLink}\n"
            
            # 把这条记录添加到总消息中
            message += Message(record_message + "\n")
        
        # 在消息最后添加统计信息
        message += Message(f"总计: {len(records)} 条过题记录")
        
        return message

# 创建插件实例
plugin = RealTimeProblemsPlugin()

async def get_recent_ac_records(minutes: int = check_gap_minutes) -> List[Dict[str, Any]]:
    """
    从数据库获取最近指定小时内的过题记录
    """
    try:
        end_time = datetime.now()
        start_time = end_time - timedelta(minutes=minutes)

        # 使用HourSubCondition获取数据库记录
        records = await HourSubCondition.get_hour_sub_records(start_time, end_time)

        return records
    except Exception as e:
        logger.error(f"获取过题记录失败: {e}")
        # 出错时返回空列表
        return []

if config.rtp_report_enable:
    @scheduler.scheduled_job(
        "cron",
        minute="0",
        hour="*",
        id="real_time_problems"
    )
    async def check_ac_records():
        """
        定时检查过题记录 - 每 check_gap_minutes 分钟自动运行一次
        """
        try:
            logger.info("开始检查过题记录...")
            
            # 1. 从数据库获取最近check_gap_minutes分钟的过题记录
            records = await get_recent_ac_records()

            # 2. 创建要发送的消息
            message = plugin.create_message(records)

            # 3. 如果没有消息就跳过（没有过题记录）
            if message is None:
                logger.info("没有过题记录，跳过发送")
                return
            
            # 4. 发送消息到配置的QQ群
            await send_to_groups(message)

            logger.info(f"成功发送 {len(records)} 条过题记录")
            
        except Exception as e:
            # 如果出错了，记录错误信息
            logger.error(f"检查过题记录时出错: {e}")
    logger.info("已启用实时过题播报功能")
else:
    logger.info(f"实时过题播报已禁用")

async def send_to_groups(message: Message):
    #发送消息到所有配置的QQ群
    try:
        bot = get_bot()

        data, _ = JsonUtils.read(
            filename=config.data_filename,
            default={
                "target_groups": []
            }
        )
        # 获取配置中的目标群组列表
        target_groups = data.get('target_groups', [])
        
        # 遍历所有配置的群组
        for group_id in target_groups:
            try:
                # 发送群消息
                await bot.send_group_msg(group_id=group_id, message=message)
                logger.info(f"消息已发送到群 {group_id}")
            except Exception as e:
                logger.error(f"发送到群 {group_id} 失败: {e}")

    except Exception as e:
        logger.error(f"发送消息失败: {e}")

@check_ac_command.handle()
async def handle_check_ac(args: Message = CommandArg()):
    try:
        # 获取用户输入的命令参数
        arg_text = args.extract_plain_text().strip()

        # 默认检查60分钟，如果用户指定了时间就用用户的时间
        minutes = 60
        if arg_text and arg_text.isdigit():
            minutes = int(arg_text)
        # 防刷屏
        if minutes > 120:
            await check_ac_command.finish(f"防刷屏设计！实时过题只能查询 120 分钟内的过题记录。参数过大：{minutes} 分钟")
        # 获取过题记录
        records = await get_recent_ac_records(minutes=minutes)
        # 创建消息
        message = plugin.create_message(records, minutes=minutes)
        # 如果有消息就发送，没有就提示无记录
        if message:
            await check_ac_command.finish(message)
        else:
            await check_ac_command.finish(f"最近'{minutes}'分钟内无过题记录")
    except FinishedException as e:
        pass
    except Exception as e:
        # 出错时发送错误信息
        await logger.info(f"检查失败: {e}")

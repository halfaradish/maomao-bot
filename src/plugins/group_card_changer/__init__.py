from nonebot import logger, get_plugin_config, get_bot, require, get_driver
from nonebot.plugin import PluginMetadata
from nonebot.adapters.onebot.v11 import Bot
from datetime import date
import asyncio

from src.common.model.model import PluginGroupEnum, PluginBadgeColor
from .config import Config
from ...common.json_utils import JsonUtils
from .holidays import get_holidays

require("nonebot_plugin_apscheduler")
from nonebot_plugin_apscheduler import scheduler

__plugin_meta__ = PluginMetadata(
    name="群昵称自动更新",
    description="根据节假日信息自动更新机器人在群聊中的昵称，项目启动时执行一次，之后每天0点自动更新",
    usage="1. 在配置文件中设置 bot_name 和 nickname_changer_schedule_enable\n2. 在 nickname_changer.json 中配置 group_whitelist\n3. 启动项目后，机器人会自动更新群昵称",
    supported_adapters={"~onebot.v11"},
    config=Config,
    extra={
        "group": PluginGroupEnum.GROUP_MANAGE.value,
        "badge_color": PluginBadgeColor.BLUE.value
    }
)

driver = get_driver()

config: Config = get_plugin_config(Config)

PLUGIN_DATA = 'nickname_changer.json'
def _read_plugin_data():
    data, _ = JsonUtils.read(
        filename=PLUGIN_DATA,
        default={
            "group_whitelist": []
        }
    )
    return data

async def change_bot_nickname():
    logger.info("开始执行昵称更换任务")
    
    try:
        bot_group_card = await get_bot_group_card()
        
        # 获取机器人实例
        bot: Bot = get_bot()
        
        # 获取机器人用户ID
        bot_user_id = int(bot.self_id)
        
        # 更新每个群的机器人昵称
        json_data = _read_plugin_data()
        group_whitelist = json_data.get('group_whitelist', [])
        for group in group_whitelist:
            group_id = int(group.get('group_id', ''))
            if not group_id:
                logger.warning(f"跳过无效的群ID: {group}")
                continue
            
            logger.info(f"正在更新群 {group_id} 的机器人昵称")
            try:
                await bot.set_group_card(
                    group_id=group_id,
                    user_id=bot_user_id,
                    card=bot_group_card
                )
                logger.info(f"成功更新群 {group_id} 的机器人昵称")
            except Exception as e:
                logger.error(f"更新群 {group_id} 的机器人昵称时出错: {e}")
            
            # 等待1秒再处理下一个群
            await asyncio.sleep(1)
        
        logger.info("所有群的机器人昵称更新完成")
    
    except Exception as e:
        logger.error(f"执行昵称更换任务时发生错误: {e}")
        raise

async def get_bot_group_card():
    try:
        holidays_info = await get_holidays()

        today = date.today()

        # 查找下一个节日
        for holiday in holidays_info:
            if holiday.date >= today:
                days_diff = (holiday.date - today).days        
                if days_diff == 0:
                    return f"{config.bot_name} | 现在是{holiday.name}!"
                else:
                    return f"{config.bot_name} | 距离{holiday.name}还有{days_diff}天"
    except Exception as e:
        logger.error(f"获取群昵称失败: {e}")
        return f"{config.bot_name}"

@driver.on_startup
async def _startup():
    if config.nickname_changer_schedule_enable:
        logger.info("项目启动时执行一次机器人昵称更新")
        try:
            await change_bot_nickname()
        except Exception as e:
            logger.error(f"启动时执行昵称更新失败: {e}")

if config.nickname_changer_schedule_enable:
    @scheduler.scheduled_job(
        'cron',
        hour=0,
        name="bot_group_card_changer"
    )
    async def _():
        await change_bot_nickname()
    logger.info("群聊名称改动功能已启动")
else:
    logger.info("群聊名称改动功能未启动")
# src/plugins/group_file_manager/hooks.py
"""启动钩子：迁移、bot 连接初始化与定时爬取"""

from nonebot import get_driver, logger, require
from nonebot.adapters.onebot.v11 import Bot
from sqlalchemy import select

from .db import MonitoredGroup, get_session
from .migrations import _ensure_fk_migration, _ensure_last_crawled_at_column
from .service import auto_crawl_all_groups

driver = get_driver()

# 获取调度器（用于定时任务）
scheduler = require("nonebot_plugin_apscheduler").scheduler


# ========== 插件启动时自动修复 FK（独立于 bot 连接） ==========

@driver.on_startup
async def _startup_fk_migration():
    """启动时最早执行：自动修复 group_files 表外键约束 + 添加 last_crawled_at 列"""
    await _ensure_last_crawled_at_column()
    await _ensure_fk_migration()


# ========== bot 连接初始化 ==========

@driver.on_bot_connect
async def init_monitored_groups(bot: Bot):
    """机器人连接时初始化 - 自动同步机器人在的所有群"""
    async with get_session(commit=False) as session:
        # 获取机器人加入的所有群
        try:
            group_list = await bot.get_group_list()
            logger.info(f"[初始化] 机器人共在 {len(group_list)} 个群中")
        except Exception as e:
            logger.error(f"[初始化] 获取群列表失败: {e}")
            group_list = []

        # 同步所有群到数据库
        for group_info in group_list:
            group_id = group_info.get("group_id")
            group_name = group_info.get("group_name", f"群{group_id}")

            if not group_id:
                continue

            result = await session.execute(select(MonitoredGroup).where(MonitoredGroup.group_id == group_id).limit(1))
            group = result.scalars().first()
            if not group:
                # 新群，自动添加
                group = MonitoredGroup(
                    group_id=group_id,
                    group_name=group_name,
                    is_active=1
                )
                session.add(group)
                logger.info(f"[初始化] 自动添加群: {group_name}({group_id})")
            else:
                # 更新群名
                group.group_name = group_name
                logger.info(f"[初始化] 更新群信息: {group_name}({group_id})")

        # 必须在 auto_crawl 之前提交，否则其独立会话看不到新群行
        await session.commit()

        # 确保 FK 约束正确（加固：即便 on_startup 未触发，这里也会兜底修复）
        await _ensure_fk_migration()

        # 自动爬取历史文件（启动时执行一次）
        logger.info("[初始化] 开始自动爬取历史文件...")
        await auto_crawl_all_groups(bot)

        # 设置定时任务：每天凌晨3点自动爬取更新
        if scheduler:
            scheduler.add_job(
                auto_crawl_all_groups,
                "cron",
                hour=3,
                minute=0,
                args=[bot],
                id="daily_crawl",
                replace_existing=True
            )
            logger.info("[初始化] 已设置定时任务：每天3:00自动爬取")

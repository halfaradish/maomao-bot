# src/plugins/group_file_manager/handlers.py
"""全部命令 matcher 与 handler（含上传事件监听）"""

from datetime import datetime
from pathlib import Path

from nonebot import logger, on_command, on_notice
from nonebot.adapters import Message
from nonebot.adapters.onebot.v11 import Bot, GroupMessageEvent, GroupUploadNoticeEvent
from nonebot.exception import FinishedException
from nonebot.params import CommandArg
from sqlalchemy import select

from .db import GroupFile, MonitoredGroup, get_session
from .migrations import _ensure_fk_migration
from .service import DATA_DIR, crawl_group_files, download_and_save
from src.common.permission import blacklist_guard, check_permission, permission_checker

# ========== 指令部分 ==========

# 指令：手动触发 FK 迁移（调试/修复用）
# handler 没有 event 形参，只能在 matcher 级挂权限点（默认拒绝，仅管理员与授权者可用）
fix_fk = on_command(
    "修复FK", aliases={"修复外键", "fixfk"}, priority=1, block=True,
    permission=permission_checker("group_file_manager:fix_fk"),
)

@fix_fk.handle()
async def handle_fix_fk():
    """手动触发 FK 迁移（调试用）"""
    await _ensure_fk_migration()
    await fix_fk.finish("FK 迁移检查已完成，请查看日志")

# 指令：查看今日新文件（优化格式）
# 只读 -> 黑名单模式，普通群友照常可用
today_files = on_command(
    "今日文件", aliases={"今天文件", "新文件"}, priority=10,
    permission=blacklist_guard(),
)

@today_files.handle()
async def handle_today_files(bot: Bot, event: GroupMessageEvent):
    """显示今天收集到的新文件（优化格式）"""
    async with get_session(commit=False) as session:
        today_start = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)

        # 查询今日该群的新文件
        result = await session.execute(
            select(GroupFile).where(
                GroupFile.group_id == event.group_id,
                GroupFile.downloaded_at >= today_start
            ).order_by(GroupFile.downloaded_at.desc())
        )
        new_files = result.scalars().all()

        if not new_files:
            msg = "📭 今天还没有收集到新文件~"
        else:
            # 构建消息（新格式）
            msg_lines = [f"📁 今日新文件 ({len(new_files)}个)", "=" * 50]

            for idx, file in enumerate(new_files[:30], 1):  # 最多显示30个
                upload_time = file.downloaded_at.strftime("%Y-%m-%d %H:%M") if file.downloaded_at else "未知"
                uploader = str(file.uploader_id) or "未知"

                msg_lines.append(f"{idx}. {file.file_name}")
                msg_lines.append(f"   群号: {file.group_id} | 上传者: {uploader}")
                msg_lines.append(f"   时间: {upload_time}")
                msg_lines.append("")  # 空行分隔

            if len(new_files) > 30:
                msg_lines.append(f"... 还有 {len(new_files)-30} 个文件未显示")

            msg = "\n".join(msg_lines)

    await today_files.finish(msg)


# 指令：查看文件存储位置
# 只读 -> 黑名单模式
file_location = on_command(
    "文件位置", aliases={"文件在哪", "存储路径"}, priority=10,
    permission=blacklist_guard(),
)

@file_location.handle()
async def handle_file_location(bot: Bot, event: GroupMessageEvent):
    """显示文件存储位置"""
    abs_path = DATA_DIR.resolve()
    msg = f"""📂 文件存储位置信息：

    本地路径: {abs_path}
    相对路径: data/group_files/

    查看方式:
    1. 直接在服务器/电脑上打开上述文件夹
    2. 使用文件资源管理器导航到该目录
    3. 数据库文件: {Path("group_files.db").resolve()}

    提示: 文件按 群号_文件ID_文件名 格式存储"""

    await file_location.finish(msg)


# 指令：手动触发历史爬取
crawl_history = on_command("爬取历史文件", aliases={"同步历史"}, priority=5)

@crawl_history.handle()
async def handle_crawl(bot: Bot, event: GroupMessageEvent, args: Message = CommandArg()):
    """手动触发爬取历史群文件，支持 --full 全量"""
    if not await check_permission(event, "group_file_manager:crawl"):
        await crawl_history.finish("您没有权限使用此功能")

    raw_args = args.extract_plain_text().strip()
    full_crawl = "--full" in raw_args or "全量" in raw_args

    mode = "全量爬取" if full_crawl else "增量爬取"
    await crawl_history.send(f"🚀 开始{mode}历史文件，请稍候...")

    try:
        count = await crawl_group_files(bot, event.group_id, full_crawl=full_crawl)
        await crawl_history.finish(f"✅ {mode}完成！共收集 {count} 个新文件")
    except FinishedException:
        # finish() 就是靠这个异常收尾的（它是 Exception 子类），
        # 不能落进下面的宽 except 再报一次「失败: FinishedException()」
        raise
    except Exception as e:
        await crawl_history.finish(f"❌ {mode}失败: {str(e)}")


# 指令：添加监控群（新增）
add_monitor = on_command("添加监控群", aliases={"监控群", "加入监控"}, priority=5)

@add_monitor.handle()
async def handle_add_monitor(bot: Bot, event: GroupMessageEvent):
    """将当前群添加到监控列表"""
    if not await check_permission(event, "group_file_manager:monitor"):
        await add_monitor.finish("您没有权限使用此功能")

    group_id = event.group_id

    # 群信息是网络调用，放在会话块外：不要跨网络调用持有 session
    try:
        group_info = await bot.get_group_info(group_id=group_id)
        group_name = group_info.get("group_name", f"群{group_id}")
    except:
        group_name = f"群{group_id}"

    async with get_session() as session:
        # 检查是否已存在
        result = await session.execute(select(MonitoredGroup).where(MonitoredGroup.group_id == group_id).limit(1))
        existing = result.scalars().first()
        if existing:
            existing.is_active = 1
            existing.group_name = group_name
            msg = f"✅ 群 {group_name}({group_id}) 已在监控列表中，已激活"
        else:
            # 添加新群
            group = MonitoredGroup(
                group_id=group_id,
                group_name=group_name,
                is_active=1
            )
            session.add(group)
            msg = f"✅ 已添加监控群: {group_name}({group_id})"

    await add_monitor.finish(msg)


# 指令：移除监控群（新增）
remove_monitor = on_command("移除监控群", aliases={"取消监控", "删除监控"}, priority=5)

@remove_monitor.handle()
async def handle_remove_monitor(bot: Bot, event: GroupMessageEvent):
    """将当前群从监控列表移除"""
    if not await check_permission(event, "group_file_manager:monitor"):
        await remove_monitor.finish("您没有权限使用此功能")

    group_id = event.group_id
    # 查到就写、查不到不写 → 用默认 commit=True，未命中分支走一次空提交
    async with get_session() as session:
        result = await session.execute(select(MonitoredGroup).where(MonitoredGroup.group_id == group_id).limit(1))
        group = result.scalars().first()
        if group:
            group.is_active = 0
            msg = f"✅ 已停止监控群: {group_id}"
        else:
            msg = f"⚠️ 群 {group_id} 不在监控列表中"

    await remove_monitor.finish(msg)


# 指令：查看监控群列表（新增）
# 会列出全站监控群（跨群信息），跟着监控管理权限走
list_monitor = on_command(
    "监控群列表", aliases={"监控列表", "查看监控"}, priority=10,
    permission=permission_checker("group_file_manager:monitor"),
)

@list_monitor.handle()
async def handle_list_monitor(bot: Bot, event: GroupMessageEvent):
    """查看所有监控群"""
    async with get_session(commit=False) as session:
        result = await session.execute(select(MonitoredGroup).where(MonitoredGroup.is_active == 1))
        groups = result.scalars().all()

        if not groups:
            msg = "📭 当前没有监控任何群\n使用「添加监控群」指令添加"
        else:
            msg_lines = ["📋 监控群列表", "=" * 40]
            for idx, group in enumerate(groups, 1):
                status = "🟢 活跃" if group.is_active else "🔴 停用"
                msg_lines.append(f"{idx}. {group.group_name}")
                msg_lines.append(f"   群号: {group.group_id} | 状态: {status}")

            msg = "\n".join(msg_lines)

    await list_monitor.finish(msg)


# ========== 事件监听 ==========

# 监听新文件上传
upload_notice = on_notice()

@upload_notice.handle()
async def handle_group_upload(bot: Bot, event: GroupUploadNoticeEvent):
    """实时监听群文件上传"""
    async with get_session(commit=False) as session:
        # 自动检查并添加新群到数据库
        result = await session.execute(select(MonitoredGroup).where(MonitoredGroup.group_id == event.group_id).limit(1))
        group = result.scalars().first()

        if not group:
            # 自动添加新群到监控列表
            try:
                group_info = await bot.get_group_info(group_id=event.group_id)
                group_name = group_info.get("group_name", f"群{event.group_id}")
            except:
                group_name = f"群{event.group_id}"

            group = MonitoredGroup(
                group_id=event.group_id,
                group_name=group_name,
                is_active=1
            )
            session.add(group)
            # 先落库新群，避免下方下载失败回滚时连带丢失群记录
            await session.commit()
            logger.info(f"[自动添加] 新群加入监控: {group_name}({event.group_id})")

        if not group.is_active:
            return  # 群被停用监控

        file_info = event.file
        logger.info(f"[新文件] {event.group_id}: {file_info.name}")

        # 下载文件
        await download_and_save(bot, event, file_info, session)

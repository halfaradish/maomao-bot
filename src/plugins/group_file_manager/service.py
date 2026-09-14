# src/plugins/group_file_manager/service.py
"""文件下载与历史爬取业务逻辑"""

import asyncio
import hashlib
from datetime import datetime
from pathlib import Path

import aiofiles
import aiohttp
from sqlalchemy import select

from nonebot import logger
from nonebot.adapters.onebot.v11 import Bot

from .db import GroupFile, MonitoredGroup, get_session

# 文件存储目录（import 时确保存在）
DATA_DIR = Path("data/group_files")
DATA_DIR.mkdir(parents=True, exist_ok=True)

# 防止同一群并发爬取
_group_crawl_locks: dict[int, asyncio.Lock] = {}


async def auto_crawl_all_groups(bot: Bot):
    """自动爬取所有监控群的历史文件（从数据库读取群号）"""
    async with get_session(commit=False) as session:
        # 从数据库读取所有活跃的监控群
        result = await session.execute(select(MonitoredGroup).where(MonitoredGroup.is_active == 1))
        groups = result.scalars().all()

        if not groups:
            logger.info("[定时任务] 没有活跃的监控群，跳过爬取")
            return

        logger.info(f"[定时任务] 开始爬取 {len(groups)} 个群的历史文件")

        for group in groups:
            try:
                logger.info(f"[定时任务] 开始爬取群 {group.group_id} ({group.group_name})")
                count = await crawl_group_files(bot, group.group_id, full_crawl=False)
                logger.info(f"[定时任务] 群 {group.group_id} 完成，新增 {count} 个文件")
            except Exception as e:
                logger.error(f"[定时任务] 群 {group.group_id} 爬取失败: {e}")


async def download_and_save(bot: Bot, event, file_info, session):
    """下载文件并保存到数据库（复用调用方传入的 session，异常时回滚调用方事务）"""
    try:
        url = await bot.get_group_file_url(
            group_id=event.group_id,
            file_id=file_info.id,
            busid=file_info.busid
        )

        file_url = url.get("url") if isinstance(url, dict) else url

        if not file_url:
            logger.error(f"[错误] 无法获取文件URL: {file_info.name}")
            return

        # 预查重：检查 file_id + group_id 是否已下载过（避免重复下载浪费带宽）
        result = await session.execute(
            select(GroupFile).where(
                GroupFile.group_id == event.group_id,
                GroupFile.file_id == file_info.id
            ).limit(1)
        )
        if result.scalars().first():
            logger.info(f"[预查重] 文件已存在: {file_info.name}")
            return

        # 生成安全文件名
        safe_name = "".join(c for c in file_info.name if c.isalnum() or c in "._-" )
        file_path = DATA_DIR / f"{event.group_id}_{file_info.id}_{safe_name}"

        async with aiohttp.ClientSession() as http_session:
            async with http_session.get(file_url) as resp:
                if resp.status == 200:
                    content = await resp.read()
                    file_hash = hashlib.md5(content).hexdigest()

                    # 全局去重检查
                    result = await session.execute(select(GroupFile).where(GroupFile.file_hash == file_hash).limit(1))
                    existing = result.scalars().first()
                    if existing:
                        logger.info(f"[去重] 文件已存在: {file_info.name}")
                        return

                    # 保存文件
                    async with aiofiles.open(file_path, 'wb') as f:
                        await f.write(content)

                    # 记录到数据库
                    new_file = GroupFile(
                        group_id=event.group_id,
                        file_id=file_info.id,
                        file_name=file_info.name,
                        file_size=file_info.size,
                        file_path=str(file_path),
                        uploader_id=event.user_id,
                        upload_time=datetime.now(),
                        file_hash=file_hash
                    )
                    session.add(new_file)
                    await session.commit()

                    logger.info(f"[保存成功] {file_info.name} ({len(content)} bytes)")
                else:
                    logger.error(f"[下载失败] HTTP {resp.status}")

    except Exception as e:
        logger.error(f"[错误] 处理文件失败: {e}")
        await session.rollback()


async def crawl_group_files(bot: Bot, group_id: int, full_crawl: bool = False) -> int:
    """爬取群历史文件（默认增量，full_crawl=True 时全量）

    Args:
        bot: Bot 实例
        group_id: QQ 群号
        full_crawl: 是否全量爬取（忽略 last_crawled_at）；
                    默认 False 即增量模式（只处理上次爬取后的新文件）
    """

    # 防止同一群并发爬取
    lock = _group_crawl_locks.setdefault(group_id, asyncio.Lock())
    if lock.locked():
        logger.warning(f"[爬取] 群 {group_id} 正在爬取中，跳过本次请求")
        return 0

    async with lock:
        async with get_session(commit=True) as session:
            # 查询群监控记录
            result = await session.execute(
                select(MonitoredGroup).where(MonitoredGroup.group_id == group_id).limit(1)
            )
            group = result.scalars().first()
            if not group:
                logger.error(f"[爬取] 群 {group_id} 不在监控列表中")
                return 0

            last_crawled_at = group.last_crawled_at
            is_incremental = not full_crawl and last_crawled_at is not None

            if is_incremental:
                logger.info(f"[爬取] 群 {group_id} 增量模式 (上次爬取: {last_crawled_at})")
                assert last_crawled_at is not None  # type narrowed by is_incremental
            else:
                reason = "全量模式（首次爬取）" if last_crawled_at is None else "全量模式（手动指定）"
                logger.info(f"[爬取] 群 {group_id} {reason}")

            downloaded_count = 0
            scanned_count = 0
            skipped_count = 0
            newest_upload_time: datetime | None = last_crawled_at

            root_files = await bot.get_group_root_files(group_id=group_id)
            files = root_files.get("files", [])
            folders = root_files.get("folders", [])

            logger.info(f"[爬取] 群 {group_id}: 发现 {len(files)} 个文件, {len(folders)} 个文件夹")

            # 辅助函数：提取 upload_time 并追踪最新时间
            def _update_newest(upload_time_ts: int | None) -> datetime | None:
                nonlocal newest_upload_time
                if upload_time_ts:
                    ut = datetime.fromtimestamp(upload_time_ts)
                    if newest_upload_time is None or ut > newest_upload_time:
                        newest_upload_time = ut
                    return ut
                return None

            # 处理根目录文件
            for file in files:
                upload_time = _update_newest(file.get("upload_time"))
                # 增量模式下：跳过 upload_time <= last_crawled_at 的旧文件
                if is_incremental and upload_time is not None and upload_time <= last_crawled_at:
                    skipped_count += 1
                    continue
                scanned_count += 1
                if await process_historical_file(bot, group_id, file, session):
                    downloaded_count += 1

            # 处理子文件夹（最多 10 个）
            for folder in folders[:10]:
                try:
                    folder_files = await bot.get_group_files_by_folder(
                        group_id=group_id,
                        folder_id=folder["folder_id"]
                    )
                    for file in folder_files.get("files", []):
                        upload_time = _update_newest(file.get("upload_time"))
                        if is_incremental and upload_time is not None and upload_time <= last_crawled_at:
                            skipped_count += 1
                            continue
                        scanned_count += 1
                        if await process_historical_file(bot, group_id, file, session):
                            downloaded_count += 1
                except Exception as e:
                    logger.error(f"[错误] 读取文件夹失败: {e}")

            # 更新 last_crawled_at（取本次扫描到的最大 upload_time，兜底用当前时间）
            new_last_crawled = newest_upload_time if newest_upload_time is not None else datetime.now()
            group.last_crawled_at = new_last_crawled

            # 退出 with 时由 get_session 统一提交（含 process_historical_file 批量新增）

            logger.info(
                f"[爬取完成] 群 {group_id}: 扫描 {scanned_count} 个文件, "
                f"新增 {downloaded_count} 个, 跳过 {skipped_count} 个已同步文件"
            )
            return downloaded_count


async def process_historical_file(bot, group_id, file_info, session) -> bool:
    """处理单个历史文件"""
    try:
        file_id = file_info.get("file_id") or file_info.get("id")
        file_name = file_info.get("file_name") or file_info.get("name")
        file_size = file_info.get("file_size") or file_info.get("size")

        # 检查是否已下载过
        result = await session.execute(
            select(GroupFile).where(
                GroupFile.group_id == group_id,
                GroupFile.file_id == file_id
            ).limit(1)
        )
        existing = result.scalars().first()

        if existing:
            return False

        # 获取下载URL
        url_info = await bot.get_group_file_url(
            group_id=group_id,
            file_id=file_id,
            busid=file_info.get("busid", 0)
        )

        file_url = url_info.get("url") if isinstance(url_info, dict) else url_info

        if not file_url:
            return False

        # 下载
        async with aiohttp.ClientSession() as http_session:
            async with http_session.get(file_url, timeout=30) as resp:
                if resp.status == 200:
                    content = await resp.read()
                    file_hash = hashlib.md5(content).hexdigest()

                    # 全局去重
                    result = await session.execute(select(GroupFile).where(GroupFile.file_hash == file_hash).limit(1))
                    dup = result.scalars().first()
                    if dup:
                        logger.info(f"[去重] 历史文件已存在: {file_name}")
                        return False

                    # 保存
                    safe_name = "".join(c for c in file_name if c.isalnum() or c in "._-" )
                    file_path = DATA_DIR / f"{group_id}_{file_id}_{safe_name}"

                    async with aiofiles.open(file_path, 'wb') as f:
                        await f.write(content)

                    # 记录
                    new_file = GroupFile(
                        group_id=group_id,
                        file_id=file_id,
                        file_name=file_name,
                        file_size=file_size,
                        file_path=str(file_path),
                        uploader_id=file_info.get("uploader", 0),
                        upload_time=datetime.fromtimestamp(file_info.get("upload_time", 0)) if file_info.get("upload_time") else None,
                        file_hash=file_hash
                    )
                    session.add(new_file)
                    logger.info(f"[历史文件] 已下载: {file_name}")
                    return True

    except Exception as e:
        logger.error(f"[错误] 处理历史文件失败: {e}")
        await session.rollback()

    return False

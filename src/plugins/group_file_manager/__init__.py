import os
import hashlib
import aiohttp
import aiofiles
from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional, List

from nonebot import on_command, get_driver, on_notice, require
from nonebot.adapters.onebot.v11 import Bot, GroupMessageEvent, GroupUploadNoticeEvent
from nonebot.params import CommandArg
from nonebot.adapters import Message

# 导入数据库模型
from .models import Session, MonitoredGroup, GroupFile, engine, Base

# 创建数据库表
Base.metadata.create_all(engine)

# 配置
DATA_DIR = Path("data/group_files")
DATA_DIR.mkdir(parents=True, exist_ok=True)

# 获取调度器（用于定时任务）
scheduler = require("nonebot_plugin_apscheduler").scheduler if require("nonebot_plugin_apscheduler") else None

# ========== 指令部分 ==========

# 指令：查看今日新文件（优化格式）
today_files = on_command("今日文件", aliases={"今天文件", "新文件"}, priority=10)

@today_files.handle()
async def handle_today_files(bot: Bot, event: GroupMessageEvent):
    """显示今天收集到的新文件（优化格式）"""
    session = Session()
    try:
        today_start = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)
        
        # 查询今日该群的新文件
        new_files = session.query(GroupFile).filter(
            GroupFile.group_id == event.group_id,
            GroupFile.downloaded_at >= today_start
        ).order_by(GroupFile.downloaded_at.desc()).all()
        
        if not new_files:
            await today_files.finish("📭 今天还没有收集到新文件~")
            return
        
        # 构建消息（新格式）
        msg_lines = [f"📁 今日新文件 ({len(new_files)}个)", "=" * 50]
        
        for idx, file in enumerate(new_files[:30], 1):  # 最多显示30个
            upload_time = file.downloaded_at.strftime("%Y-%m-%d %H:%M") if file.downloaded_at else "未知"
            uploader = file.uploader_name or str(file.uploader_id) or "未知"
            
            msg_lines.append(f"{idx}. {file.file_name}")
            msg_lines.append(f"   群号: {file.group_id} | 上传者: {uploader}")
            msg_lines.append(f"   时间: {upload_time}")
            msg_lines.append("")  # 空行分隔
        
        if len(new_files) > 30:
            msg_lines.append(f"... 还有 {len(new_files)-30} 个文件未显示")
        
        await today_files.finish("\n".join(msg_lines))
        
    finally:
        session.close()


# 指令：查看文件存储位置
file_location = on_command("文件位置", aliases={"文件在哪", "存储路径"}, priority=10)

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
async def handle_crawl(bot: Bot, event: GroupMessageEvent):
    """手动触发爬取历史群文件"""
    await crawl_history.send("🚀 开始爬取历史文件，请稍候...")
    
    try:
        count = await crawl_group_files(bot, event.group_id)
        await crawl_history.finish(f"✅ 爬取完成！共收集 {count} 个新文件")
    except Exception as e:
        await crawl_history.finish(f"❌ 爬取失败: {str(e)}")


# 指令：添加监控群（新增）
add_monitor = on_command("添加监控群", aliases={"监控群", "加入监控"}, priority=5)

@add_monitor.handle()
async def handle_add_monitor(bot: Bot, event: GroupMessageEvent):
    """将当前群添加到监控列表"""
    session = Session()
    try:
        group_id = event.group_id
        
        # 获取群信息
        try:
            group_info = await bot.get_group_info(group_id=group_id)
            group_name = group_info.get("group_name", f"群{group_id}")
        except:
            group_name = f"群{group_id}"
        
        # 检查是否已存在
        existing = session.query(MonitoredGroup).filter_by(group_id=group_id).first()
        if existing:
            existing.is_active = 1
            existing.group_name = group_name
            session.commit()
            await add_monitor.finish(f"✅ 群 {group_name}({group_id}) 已在监控列表中，已激活")
            return
        
        # 添加新群
        group = MonitoredGroup(
            group_id=group_id,
            group_name=group_name,
            is_active=1
        )
        session.add(group)
        session.commit()
        
        await add_monitor.finish(f"✅ 已添加监控群: {group_name}({group_id})")
        
    finally:
        session.close()


# 指令：移除监控群（新增）
remove_monitor = on_command("移除监控群", aliases={"取消监控", "删除监控"}, priority=5)

@remove_monitor.handle()
async def handle_remove_monitor(bot: Bot, event: GroupMessageEvent):
    """将当前群从监控列表移除"""
    session = Session()
    try:
        group_id = event.group_id
        
        group = session.query(MonitoredGroup).filter_by(group_id=group_id).first()
        if group:
            group.is_active = 0
            session.commit()
            await remove_monitor.finish(f"✅ 已停止监控群: {group_id}")
        else:
            await remove_monitor.finish(f"⚠️ 群 {group_id} 不在监控列表中")
        
    finally:
        session.close()


# 指令：查看监控群列表（新增）
list_monitor = on_command("监控群列表", aliases={"监控列表", "查看监控"}, priority=10)

@list_monitor.handle()
async def handle_list_monitor(bot: Bot, event: GroupMessageEvent):
    """查看所有监控群"""
    session = Session()
    try:
        groups = session.query(MonitoredGroup).filter_by(is_active=1).all()
        
        if not groups:
            await list_monitor.finish("📭 当前没有监控任何群\n使用「添加监控群」指令添加")
            return
        
        msg_lines = ["📋 监控群列表", "=" * 40]
        for idx, group in enumerate(groups, 1):
            status = "🟢 活跃" if group.is_active else "🔴 停用"
            msg_lines.append(f"{idx}. {group.group_name}")
            msg_lines.append(f"   群号: {group.group_id} | 状态: {status}")
        
        await list_monitor.finish("\n".join(msg_lines))
        
    finally:
        session.close()


# ========== 自动定时任务 ==========

async def auto_crawl_all_groups(bot: Bot):
    """自动爬取所有监控群的历史文件（从数据库读取群号）"""
    session = Session()
    try:
        # 从数据库读取所有活跃的监控群
        groups = session.query(MonitoredGroup).filter_by(is_active=1).all()
        
        if not groups:
            print("[定时任务] 没有活跃的监控群，跳过爬取")
            return
        
        print(f"[定时任务] 开始爬取 {len(groups)} 个群的历史文件")
        
        for group in groups:
            try:
                print(f"[定时任务] 开始爬取群 {group.group_id} ({group.group_name})")
                count = await crawl_group_files(bot, group.group_id)
                print(f"[定时任务] 群 {group.group_id} 完成，新增 {count} 个文件")
            except Exception as e:
                print(f"[定时任务] 群 {group.group_id} 爬取失败: {e}")
                
    finally:
        session.close()


# ========== 事件监听 ==========

# 监听新文件上传
upload_notice = on_notice()

@upload_notice.handle()
async def handle_group_upload(bot: Bot, event: GroupUploadNoticeEvent):
    """实时监听群文件上传"""
    session = Session()
    try:
        # 自动检查并添加新群到数据库
        group = session.query(MonitoredGroup).filter_by(group_id=event.group_id).first()
        
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
            session.commit()
            print(f"[自动添加] 新群加入监控: {group_name}({event.group_id})")
        
        if not group.is_active:
            return  # 群被停用监控
        
        file_info = event.file
        print(f"[新文件] {event.group_id}: {file_info.name}")
        
        # 下载文件
        await download_and_save(bot, event, file_info, session)
        
    finally:
        session.close()


async def download_and_save(bot: Bot, event, file_info, session):
    """下载文件并保存到数据库"""
    try:
        url = await bot.get_group_file_url(
            group_id=event.group_id,
            file_id=file_info.id,
            busid=file_info.busid
        )
        
        file_url = url.get("url") if isinstance(url, dict) else url
        
        if not file_url:
            print(f"[错误] 无法获取文件URL: {file_info.name}")
            return
        
        # 生成安全文件名
        safe_name = "".join(c for c in file_info.name if c.isalnum() or c in "._-")
        file_path = DATA_DIR / f"{event.group_id}_{file_info.id}_{safe_name}"
        
        async with aiohttp.ClientSession() as http_session:
            async with http_session.get(file_url) as resp:
                if resp.status == 200:
                    content = await resp.read()
                    file_hash = hashlib.md5(content).hexdigest()
                    
                    # 全局去重检查
                    existing = session.query(GroupFile).filter_by(file_hash=file_hash).first()
                    if existing:
                        print(f"[去重] 文件已存在: {file_info.name}")
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
                    session.commit()
                    
                    print(f"[保存成功] {file_info.name} ({len(content)} bytes)")
                else:
                    print(f"[下载失败] HTTP {resp.status}")
                    
    except Exception as e:
        print(f"[错误] 处理文件失败: {e}")
        session.rollback()


async def crawl_group_files(bot: Bot, group_id: int) -> int:
    """爬取群历史文件"""
    session = Session()
    downloaded_count = 0
    
    try:
        root_files = await bot.get_group_root_files(group_id=group_id)
        
        files = root_files.get("files", [])
        folders = root_files.get("folders", [])
        
        print(f"[爬取] 群 {group_id}: 发现 {len(files)} 个文件, {len(folders)} 个文件夹")
        
        # 处理根目录文件
        for file in files:
            if await process_historical_file(bot, group_id, file, session):
                downloaded_count += 1
        
        # 处理子文件夹
        for folder in folders[:10]:  # 增加到10个文件夹
            try:
                folder_files = await bot.get_group_files_by_folder(
                    group_id=group_id,
                    folder_id=folder["folder_id"]
                )
                for file in folder_files.get("files", []):
                    if await process_historical_file(bot, group_id, file, session):
                        downloaded_count += 1
            except Exception as e:
                print(f"[错误] 读取文件夹失败: {e}")
        
        session.commit()
        return downloaded_count
        
    finally:
        session.close()


async def process_historical_file(bot, group_id, file_info, session) -> bool:
    """处理单个历史文件"""
    try:
        file_id = file_info.get("file_id") or file_info.get("id")
        file_name = file_info.get("file_name") or file_info.get("name")
        file_size = file_info.get("file_size") or file_info.get("size")
        
        # 检查是否已下载过
        existing = session.query(GroupFile).filter_by(
            group_id=group_id,
            file_id=file_id
        ).first()
        
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
                    dup = session.query(GroupFile).filter_by(file_hash=file_hash).first()
                    if dup:
                        print(f"[去重] 历史文件已存在: {file_name}")
                        return False
                    
                    # 保存
                    safe_name = "".join(c for c in file_name if c.isalnum() or c in "._-")
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
                    print(f"[历史文件] 已下载: {file_name}")
                    return True
                    
    except Exception as e:
        print(f"[错误] 处理历史文件失败: {e}")
    
    return False


# ========== 初始化 ==========

driver = get_driver()

@driver.on_bot_connect
async def init_monitored_groups(bot: Bot):
    """机器人连接时初始化 - 自动同步机器人在的所有群"""
    session = Session()
    try:
        # 获取机器人加入的所有群
        try:
            group_list = await bot.get_group_list()
            print(f"[初始化] 机器人共在 {len(group_list)} 个群中")
        except Exception as e:
            print(f"[初始化] 获取群列表失败: {e}")
            group_list = []
        
        # 同步所有群到数据库
        for group_info in group_list:
            group_id = group_info.get("group_id")
            group_name = group_info.get("group_name", f"群{group_id}")
            
            if not group_id:
                continue
            
            group = session.query(MonitoredGroup).filter_by(group_id=group_id).first()
            if not group:
                # 新群，自动添加
                group = MonitoredGroup(
                    group_id=group_id,
                    group_name=group_name,
                    is_active=1
                )
                session.add(group)
                print(f"[初始化] 自动添加群: {group_name}({group_id})")
            else:
                # 更新群名
                group.group_name = group_name
                print(f"[初始化] 更新群信息: {group_name}({group_id})")
        
        session.commit()
        
        # 自动爬取历史文件（启动时执行一次）
        print("[初始化] 开始自动爬取历史文件...")
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
            print("[初始化] 已设置定时任务：每天3:00自动爬取")
        
    finally:
        session.close()
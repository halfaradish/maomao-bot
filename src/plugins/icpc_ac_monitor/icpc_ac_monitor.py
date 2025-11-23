# src/plugins/icpc_ac_monitor/icpc_ac_monitor.py
"""
ICPC AC Monitor Plugin  ‑  单文件全局版
1. data/icpc_ac_monitor.json 同时存目标群、学校、监控比赛
2. 本地可手动改群号/学校，代码只读写 monitors 部分
3. 开始/取消都是全局开关，所有目标群同步收 AC 推送
"""

import json
import os
import tempfile
import threading
import time
from pathlib import Path
from typing import Dict, List, Any
import asyncio
import requests

from nonebot import logger, on_command, get_bot, get_driver
from nonebot.adapters.onebot.v11 import Bot, Event, Message
from nonebot.params import CommandArg

# ==============================================================================
# 一、路径相关
# ==============================================================================
# 计算项目根目录：插件文件向上 4 级就是项目根
BASE_DIR = Path(__file__).resolve().parent.parent.parent.parent
# 单文件配置路径：data/icpc_ac_monitor.json
CONF_FILE = BASE_DIR / "data" / "icpc_ac_monitor.json"
# 若 data 目录不存在则自动创建
CONF_FILE.parent.mkdir(exist_ok=True)

# ==============================================================================
# 二、配置读写函数（原子写入，防写残）
# ==============================================================================
def load_conf() -> Dict[str, Any]:
    """
    加载整个 json 配置；
    若文件不存在则生成模板（目标群为空，学校默认广西大学）。
    """
    if not CONF_FILE.exists():
        tpl = {"target_groups": [], "schools": ["广西大学"], "monitors": {}}
        save_conf(tpl)
        return tpl
    try:
        with CONF_FILE.open("r", encoding="utf-8") as f:
            return json.load(f)
    except Exception as e:
        logger.warning(f"读取配置失败：{e}，返回空模板")
        return {"target_groups": [], "schools": [], "monitors": {}}

def save_conf(data: Dict[str, Any]):
    """
    原子写入：先写临时文件，再 replace，避免写一半崩溃导致 JSON 损坏。
    """
    try:
        with tempfile.NamedTemporaryFile(
            "w", encoding="utf-8", delete=False, dir=CONF_FILE.parent, prefix="tmp_"
        ) as tmp:
            json.dump(data, tmp, ensure_ascii=False, indent=2)
            tmp.flush()
            os.fsync(tmp.fileno())          # 强制落盘
        os.replace(tmp.name, CONF_FILE)     # 瞬间替换，几乎不可能出现半文件
    except Exception as e:
        logger.error(f"保存配置失败：{e}")
        try:
            os.unlink(tmp.name)             # 清理临时文件
        except:
            pass

# ==============================================================================
# 三、启动时一次性加载配置
# ==============================================================================
conf = load_conf()
# 目标群号列表（推送白名单）——你手动改 json 即可
TARGET_GROUPS: List[int] = conf["target_groups"]
# 监控学校列表——你手动改 json 即可
SCHOOLS: List[str] = conf["schools"]
# 正在全局监控的比赛字典（url 为 key）
memory: Dict[str, Any] = conf["monitors"]

# ==============================================================================
# 四、命令注册
# ==============================================================================
start_monitor = on_command("开始监控", aliases={"monitor"}, priority=5)
stop_monitor = on_command("取消监控", aliases={"stop"}, priority=5)
logger.info("icpc_ac_monitor 插件加载完成（单文件全局版）")

# ==============================================================================
# 五、开始监控 —— 全局开关
# ==============================================================================
@start_monitor.handle()
async def handle_start_monitor(bot: Bot, event: Event, args: Message = CommandArg()):
    # 保存 bot 实例供子线程使用
    set_bot_instance(bot)
    """
    任意目标群发送：
      开始监控 https://board.xcpcio.com/icpc/50th/shenyang
    效果：
      1. 若已全局监控 → 提示已存在；
      2. 否则拉 team.json → 过滤 schools → 创建全局记录 →
         启动唯一线程 → 全部 TARGET_GROUPS 同步收 AC。
    """
    # 取 URL 并统一成 cdn 域名
    url = args.extract_plain_text().strip()
    if not url or not url.startswith("https://board.xcpcio.com"):
        await start_monitor.finish(
            "请输入正确比赛网址，例如：\n开始监控 https://board.xcpcio.com/icpc/50th/shenyang"
        )
    
    # 将 board.xcpcio.com 转换为 cdn.xcpcio.com/data（数据API端点）
    original_url = url.rstrip("/")
    base_url = original_url.replace("https://board.xcpcio.com", "https://cdn.xcpcio.com/data")

    # 全局重复判断
    if base_url in memory:
        await start_monitor.finish("该比赛已在监控列表中，无需重复添加。")

    # 拉队伍并过滤学校
    try:
        resp = requests.get(f"{base_url}/team.json", timeout=5, headers={"User-Agent": "Mozilla/5.0"})
        data = resp.json()

        # 兼容数组和字典两种格式
        if isinstance(data, list):
            team_list = data
        elif isinstance(data, dict):
            team_list = list(data.values())
        else:
            raise ValueError("team.json 返回的数据不是列表或字典")

    except Exception as e:
        logger.error(f"获取队伍数据失败：{e}, 内容: {resp.text[:500]}")
        await start_monitor.finish(f"获取队伍数据失败：{e}")

    # 过滤学校
    teams = [t for t in team_list if t.get("organization") in SCHOOLS]
    if not teams:
        await start_monitor.finish(f"{base_url.split('/')[-1]} 中没有指定学校队伍")

    # 创建全局记录（内存 + 文件）
    # 确保 team_id 统一为字符串类型，避免类型不匹配
    team_ids_list = []
    id_to_name_dict = {}
    for t in teams:
        tid_raw = t.get("id") or t.get("team_id")
        tid = str(tid_raw) if tid_raw is not None else ""
        team_ids_list.append(tid)
        id_to_name_dict[tid] = t.get("name", "未知队伍")
    
    meta = {
        "comp_name": base_url.split("/")[-1],
        "run_url": f"{base_url}/run.json",
        "team_ids": team_ids_list,
        "id_to_name": id_to_name_dict,
        "already_solved": [],
    }
    logger.info(f"监控配置：队伍数量={len(team_ids_list)}, 目标群={len(TARGET_GROUPS)}个")
    memory[base_url] = meta
    conf["monitors"] = memory
    save_conf(conf)
    await start_monitor.send(f"已添加全局监控：{meta['comp_name']}")

    # 启动唯一轮询线程
    thread = threading.Thread(target=monitor_loop, args=(base_url,), daemon=True)
    memory[base_url]["thread"] = thread
    thread.start()

# ==============================================================================
# 六、取消监控 —— 全局关闭
# ==============================================================================
@stop_monitor.handle()
async def handle_stop_monitor(bot: Bot, event: Event, args: Message = CommandArg()):
    """
    任意目标群发送：
      取消监控 https://board.xcpcio.com/icpc/50th/shenyang
    效果：
      直接删整条记录 → 线程自然结束 → 全部目标群不再收推送。
    """
    url = args.extract_plain_text().strip()
    if not url or not url.startswith("https://board.xcpcio.com"):
        await stop_monitor.finish("请输入要暂停的比赛网址，例如：\n取消监控 https://board.xcpcio.com/icpc/50th/shenyang")
    base_url = url.rstrip("/").replace("https://board.xcpcio.com", "https://cdn.xcpcio.com/data")

    meta = memory.pop(base_url, None)
    if not meta:
        await stop_monitor.finish("目前没有该比赛的监控～")

    # 立刻落盘
    conf["monitors"] = memory
    save_conf(conf)
    await stop_monitor.finish(f"已完全停止监控：{meta['comp_name']}")

# -------------------- 轮询推送（固定推全部 TARGET_GROUPS） --------------------
def monitor_loop(base_url: str):
    logger.info(f"监控线程已启动，比赛 {base_url}")

    # 使用全局保存的主事件循环
    loop = _main_event_loop
    
    if loop is None or not loop.is_running():
        # 尝试从 driver 获取
        try:
            driver = get_driver()
            if hasattr(driver, '_loop'):
                loop = driver._loop
            elif hasattr(driver, 'loop'):
                loop = driver.loop
            if not loop or not loop.is_running():
                logger.error("无法获取运行中的主事件循环，推送将失败")
                loop = None
        except Exception as e:
            logger.error(f"获取事件循环失败：{e}")
            loop = None

    while base_url in memory:
        meta = memory[base_url]
        try:
            resp = requests.get(meta["run_url"], timeout=10, headers={"User-Agent": "Mozilla/5.0"})
            resp.raise_for_status()
            runs = resp.json()
        except Exception as e:
            logger.warning(f"获取 run.json 失败：{e}")
            time.sleep(5)
            continue

        # 检查目标群配置
        if not TARGET_GROUPS:
            logger.warning(f"TARGET_GROUPS 为空，无法推送消息")
            time.sleep(30)
            continue

        # 初始化 seen_ids，保证不重复推送
        if "seen_ids" not in meta:
            meta["seen_ids"] = []
            logger.info(f"初始化 seen_ids 为空（首次运行，将推送所有历史提交）")

        seen = set(meta["seen_ids"])
        seen_count_before = len(seen)  # 记录处理前的数量，用于判断是否需要保存
        
        # 确保 team_ids 中的值都是字符串类型，用于比较
        team_ids_set = {str(tid) for tid in meta["team_ids"]}
        
        total_runs = len(runs)
        new_submissions = 0
        matched_runs = 0
        skipped_by_team = 0

        for run in runs:
            # 先过滤不是我们学校的队伍 - 确保类型一致
            # 只处理监控队伍的提交，减少存储空间
            run_team_id_raw = run.get("team_id")
            run_team_id = str(run_team_id_raw) if run_team_id_raw is not None else ""
            
            # 如果不是监控的队伍，直接跳过，不加入 seen_ids
            if run_team_id not in team_ids_set:
                skipped_by_team += 1
                continue
            
            # 只对监控队伍的提交生成唯一标识并加入 seen_ids
            matched_runs += 1
            
            # run.json 可能没有 'id' 字段，使用组合键作为唯一标识
            # 使用 team_id + problem_id + timestamp 作为唯一标识
            try:
                # 先尝试使用 id 字段（如果存在）
                if "id" in run:
                    rid = str(run["id"])
                else:
                    # 如果没有 id，使用组合键
                    problem_id = str(run.get("problem_id", ""))
                    timestamp = str(run.get("timestamp", ""))
                    # 如果没有 timestamp，尝试使用其他字段
                    if not timestamp or timestamp == "":
                        timestamp = str(run.get("time", run.get("submission_time", run.get("submitted_at", ""))))
                    rid = f"{run_team_id}_{problem_id}_{timestamp}"
                    if rid == f"{run_team_id}__":  # 如果所有字段都为空，跳过
                        continue
            except Exception:
                continue

            # 已处理过的提交跳过（只检查监控队伍的提交）
            if rid in seen:
                continue
            seen.add(rid)

            # problem_id 转 A/B/C...
            try:
                pid = int(run["problem_id"])
                prob_char = chr(ord("A") + pid)
            except (KeyError, ValueError, TypeError):
                prob_char = "?"

            team_name = meta["id_to_name"].get(run_team_id, "未知队伍")
            status = run.get("status", "UNKNOWN")

            # 构建消息
            msg = f"[{meta['comp_name']}] {team_name} 已 {status} 了 {prob_char} 题！"
            logger.info(f"检测到新提交：{msg}")

            # 线程安全推送给所有目标群
            # 使用主事件循环来执行推送，确保 get_bot() 能正确工作
            for gid in TARGET_GROUPS:
                try:
                    # 检查事件循环是否可用
                    if loop is None:
                        logger.error(f"事件循环不可用，无法推送消息到群 {gid}")
                        continue
                    
                    if not loop.is_running():
                        logger.error(f"事件循环未运行，无法推送消息到群 {gid}")
                        continue
                    
                    # 使用 run_coroutine_threadsafe 在主事件循环中执行
                    future = asyncio.run_coroutine_threadsafe(send_ac_msg(int(gid), msg), loop)
                    
                    # 等待推送完成，并捕获异常
                    try:
                        future.result(timeout=10)
                    except asyncio.TimeoutError:
                        logger.error(f"推送任务超时（群{gid}）")
                    except Exception as e:
                        logger.error(f"推送任务执行失败（群{gid}）：{e}")
                except Exception as e:
                    logger.error(f"调度推送任务失败（群{gid}）：{e}")
            
            new_submissions += 1

        # 保存已处理过的 run.id（内存）
        meta["seen_ids"] = list(seen)
        
        # 定期保存到配置文件（避免重启后重复推送）
        # 如果有新提交或seen_ids数量变化，立即保存
        if new_submissions > 0 or len(seen) != seen_count_before:
            # 创建干净的配置副本，移除不能序列化的对象（如Thread）
            clean_memory = {}
            for url, m in memory.items():
                clean_meta = {k: v for k, v in m.items() if k != "thread"}
                clean_memory[url] = clean_meta
            
            conf["monitors"] = clean_memory
            save_conf(conf)
        
        if new_submissions > 0:
            logger.info(f"本轮检测到 {new_submissions} 个新提交，已推送到 {len(TARGET_GROUPS)} 个群")
        elif matched_runs == 0 and total_runs > 0 and len(seen) == 0:
            # 只在首次运行且没有匹配时输出警告
            logger.warning(f"警告：有 {total_runs} 条提交但匹配队伍数为0，请检查配置")

        time.sleep(5)



# ==============================================================================
# 八、异步发群消息
# ==============================================================================
# 全局变量：存储 bot 实例和主事件循环（在启动时设置）
_cached_bot = None
_main_event_loop = None

def set_bot_instance(bot: Bot):
    """在启动时设置 bot 实例和主事件循环"""
    global _cached_bot, _main_event_loop
    _cached_bot = bot
    try:
        _main_event_loop = asyncio.get_running_loop()
    except RuntimeError:
        try:
            _main_event_loop = asyncio.get_event_loop()
            if not _main_event_loop.is_running():
                _main_event_loop = None
        except Exception:
            _main_event_loop = None

async def send_ac_msg(group_id: int, message: str):
    """
    利用缓存的 bot 实例或 get_bot() 异步向指定群发消息。
    失败时只记日志，不中断线程。
    """
    try:
        # 优先使用缓存的 bot 实例
        bot = _cached_bot
        if bot is None:
            # 如果缓存中没有，尝试获取
            try:
                bot = get_bot()
            except Exception as e:
                logger.error(f"无法获取 bot 实例：{e}")
                raise
        
        result = await bot.send_group_msg(group_id=group_id, message=message)
        return result
    except Exception as e:
        logger.error(f"推送失败（群{group_id}）：{e}")
        raise

# ==============================================================================
# 九、启动时恢复持久化监控
# ==============================================================================
def restore_on_startup():
    """
    bot 启动时遍历 memory，为每个比赛重新启动后台线程。
    """
    global _main_event_loop
    
    # 尝试设置主事件循环（如果还没有设置）
    if _main_event_loop is None:
        try:
            _main_event_loop = asyncio.get_running_loop()
        except RuntimeError:
            try:
                loop = asyncio.get_event_loop()
                if loop.is_running():
                    _main_event_loop = loop
            except Exception:
                pass
    
    if not memory:
        logger.info("icpc_ac_monitor: 没有需要恢复的监控任务")
        return
    
    if not TARGET_GROUPS:
        logger.warning("icpc_ac_monitor: TARGET_GROUPS 为空，已恢复的监控将无法推送消息")
    
    for url, meta in list(memory.items()):      # list 防止迭代时修改
        # 确保 team_ids 中的 ID 都是字符串类型（兼容旧配置）
        if "team_ids" in meta:
            meta["team_ids"] = [str(tid) for tid in meta["team_ids"]]
        # 确保 id_to_name 的 key 都是字符串
        if "id_to_name" in meta:
            meta["id_to_name"] = {str(k): v for k, v in meta["id_to_name"].items()}
        
        thread = threading.Thread(target=monitor_loop, args=(url,), daemon=True)
        meta["thread"] = thread
        thread.start()
        # 显示更清晰的信息：显示原始URL（如果可能）和数据URL
        display_url = url.replace("https://cdn.xcpcio.com/data", "https://board.xcpcio.com")
        logger.info(f"[持久化] 比赛 {meta['comp_name']} 已恢复（{display_url}），将推送给 {len(TARGET_GROUPS)} 个目标群")

# 使用启动钩子来恢复监控（此时事件循环已运行）
@get_driver().on_startup
async def startup_restore():
    """在 bot 启动时恢复监控任务"""
    global _main_event_loop
    try:
        _main_event_loop = asyncio.get_running_loop()
    except Exception:
        pass
    restore_on_startup()
# -------------------- 新增指令：赛时过题（按队输出） --------------------
from nonebot import on_command
from nonebot.adapters.onebot.v11 import Message
from nonebot.params import CommandArg

query_status = on_command("赛时过题", aliases={"过题情况"}, priority=5)

def _to_base_url(url: str) -> str:
    """把 board 域名转换为 cdn 数据域名并规范化。"""
    return url.rstrip("/").replace("https://board.xcpcio.com", "https://cdn.xcpcio.com/data")

def _pid_to_char(pid: int) -> str:
    """0 -> A, 1 -> B ... 超出则返回数字形式"""
    try:
        n = int(pid)
        if 0 <= n < 26:
            return chr(ord("A") + n)
        else:
            return str(pid)
    except Exception:
        return "?"

def fetch_ac_status(base_url: str, schools: List[str]) -> Dict[str, Any]:
    """
    在同步线程中执行：拉 team.json 和 run.json，返回统计结果字典：
    {
      "comp_name": "zhengzhou",
      "teams": [
         {"id": "67", "name": "远航者的幻想乡", "solved": ["A","C"], "count": 2},
         ...
      ]
    }
    """
    result = {"comp_name": base_url.split("/")[-1], "teams": []}
    try:
        t_resp = requests.get(f"{base_url}/team.json", timeout=8, headers={"User-Agent": "Mozilla/5.0"})
        t_resp.raise_for_status()
        teams = t_resp.json()  # list of team objects
    except Exception as e:
        raise RuntimeError(f"读取 team.json 失败：{e}")

    try:
        r_resp = requests.get(f"{base_url}/run.json", timeout=8, headers={"User-Agent": "Mozilla/5.0"})
        r_resp.raise_for_status()
        runs = r_resp.json()  # list of run objects
    except Exception as e:
        raise RuntimeError(f"读取 run.json 失败：{e}")

    # 过滤出我们关注的正式队伍（organization in schools）
    # team entries example: {"id":"67","name":"远航者的幻想乡","organization":"广西大学", ...}
    id_to_name = {}
    watched_team_ids = set()
    for t in teams:
        try:
            tid = t.get("id")
        except Exception:
            continue
        org = t.get("organization", "")
        if org in schools:
            watched_team_ids.add(tid)
            id_to_name[tid] = t.get("name", str(tid))

    # 如果没有关注的队伍，直接返回空 teams
    if not watched_team_ids:
        return result

    # 统计每队已 AC 的题目集合（去重）
    accept_statuses = {"CORRECT", "ACCEPTED", "AC"}  # 兼容多种写法
    team_solved: Dict[str, set] = {tid: set() for tid in watched_team_ids}
    for run in runs:
        tid = run.get("team_id")
        if tid not in watched_team_ids:
            continue
        status = run.get("status", "")
        if status not in accept_statuses:
            continue
        pid = run.get("problem_id")
        # 把 pid 转为字母
        ch = _pid_to_char(pid)
        team_solved[tid].add(ch)

    # 组装结果
    for tid in sorted(watched_team_ids, key=lambda x: id_to_name.get(x, x)):
        solved_list = sorted(team_solved.get(tid, []), key=lambda s: (len(s) > 1, s))  # 尽量按字母排序，数字题号靠后
        result["teams"].append({
            "id": tid,
            "name": id_to_name.get(tid, str(tid)),
            "solved": solved_list,
            "count": len(solved_list),
        })
    return result

@query_status.handle()
async def handle_query_status(bot: Bot, event: Event, args: Message = CommandArg()):
    """
    用法：
      @bot 赛时过题 https://board.xcpcio.com/ccpc/11th/zhengzhou
    输出（每队一行）：
      远航者的幻想乡 在 zhengzhou 已过了 A,B 共 2 题
    """
    text = args.extract_plain_text().strip()
    if not text:
        await query_status.finish("请在命令后提供比赛链接，例如：\n@bot 赛时过题 https://board.xcpcio.com/ccpc/11th/zhengzhou")

    # 只取第一个看起来像 URL 的部分（本命令只处理一个 URL）
    url = text.split()[0]
    if not url.startswith("https://board.xcpcio.com"):
        await query_status.finish("请输入合法的 board.xcpcio.com 比赛链接，例如：\n@bot 赛时过题 https://board.xcpcio.com/ccpc/11th/zhengzhou")

    base_url = _to_base_url(url)

    # 在线程池里同步请求远程数据，避免阻塞 nonebot 事件循环
    try:
        info = await asyncio.to_thread(fetch_ac_status, base_url, SCHOOLS)
    except Exception as e:
        await query_status.finish(f"查询失败：{e}")

    comp_name = info.get("comp_name", base_url.split("/")[-1])
    teams = info.get("teams", [])

    if not teams:
        await query_status.finish(f"{comp_name} 中没有来自配置 schools 的队伍（{', '.join(SCHOOLS)}）或没有数据。")

    # 构建消息，每队一行
    lines = []
    for t in teams:
        name = t["name"]
        solved = t["solved"]
        count = t["count"]
        if count == 0:
            lines.append(f"{name} 在 {comp_name} 还未通过任何题目")
        else:
            # 按你的示例要求，用逗号分隔题号（不加空格更紧凑）
            lines.append(f"{name} 在 {comp_name} 已过了 {','.join(solved)} 共 {count} 题")

    # 如果行数过多可截断或分页——这里一次性返回全部
    msg = "\n".join(lines)
    await query_status.finish(msg)

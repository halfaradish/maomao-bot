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

from nonebot import logger, on_command, get_bot
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
    base_url = url.rstrip("/").replace("https://board.xcpcio.com", "https://cdn.xcpcio.com/data")

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
    meta = {
        "comp_name": base_url.split("/")[-1],
        "run_url": f"{base_url}/run.json",
        "team_ids": [t.get("id") or t.get("team_id") for t in teams],
        "id_to_name": {
            t.get("id") or t.get("team_id"): t.get("name", "未知队伍") for t in teams
        },
        "already_solved": [],
    }
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

    # 在子线程创建自己的事件循环（必须）
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)

    while base_url in memory:
        meta = memory[base_url]
        try:
            resp = requests.get(meta["run_url"], timeout=5, headers={"User-Agent": "Mozilla/5.0"})
            runs = resp.json()  # run.json 是一个 list
        except Exception as e:
            logger.warning(f"获取 run.json 失败：{e}")
            time.sleep(5)
            continue

        # 初始化 seen_ids，保证不重复推送
        if "seen_ids" not in meta:
            meta["seen_ids"] = []

        seen = set(meta["seen_ids"])

        for run in runs:
            try:
                rid = int(run["id"])
            except Exception:
                continue

            # 已处理过的提交跳过
            if rid in seen:
                continue
            seen.add(rid)

            # 过滤不是我们学校的队伍
            if run["team_id"] not in meta["team_ids"]:
                continue

            # problem_id 转 A/B/C...
            try:
                pid = int(run["problem_id"])
                prob_char = chr(ord("A") + pid)
            except Exception:
                prob_char = "?"

            team_name = meta["id_to_name"].get(run["team_id"], "未知队伍")
            status = run.get("status", "UNKNOWN")

            # 构建消息
            msg = f"[{meta['comp_name']}] {team_name} 已 {status} 了 {prob_char} 题！"

            # 线程安全推送给所有目标群
            for gid in TARGET_GROUPS:
                asyncio.run_coroutine_threadsafe(send_ac_msg(int(gid), msg), loop)

        # 保存已处理过的 run.id
        meta["seen_ids"] = list(seen)

        time.sleep(5)



# ==============================================================================
# 八、异步发群消息
# ==============================================================================
async def send_ac_msg(group_id: int, message: str):
    """
    利用 NoneBot 的 get_bot() 异步向指定群发消息。
    失败时只记日志，不中断线程。
    """
    try:
        bot = get_bot()
        await bot.send_group_msg(group_id=group_id, message=message)
    except Exception as e:
        logger.error(f"推送失败：{e}")

# ==============================================================================
# 九、启动时恢复持久化监控
# ==============================================================================
def restore_on_startup():
    """
    bot 启动时遍历 memory，为每个比赛重新启动后台线程。
    """
    for url, meta in list(memory.items()):      # list 防止迭代时修改
        thread = threading.Thread(target=monitor_loop, args=(url,), daemon=True)
        meta["thread"] = thread
        thread.start()
        logger.info(f"[持久化] 比赛 {meta['comp_name']} 已恢复，将推送给 {len(TARGET_GROUPS)} 个目标群")

# 立即执行恢复
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

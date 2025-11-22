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
        await start_monitor.finish("请输入正确比赛网址，例如：\n开始监控 https://board.xcpcio.com/icpc/50th/shenyang")
    base_url = url.rstrip("/").replace("https://board.xcpcio.com", "https://cdn.xcpcio.com/data")

    # 全局重复判断
    if base_url in memory:
        await start_monitor.finish("该比赛已在监控列表中，无需重复添加。")

    # 拉队伍并过滤学校
    try:
        resp = requests.get(f"{base_url}/team.json", timeout=5, headers={"User-Agent": "Mozilla/5.0"})
        team_list = resp.json()
    except Exception as e:
        logger.error(f"获取队伍数据失败：{e}")
        await start_monitor.finish(f"获取队伍数据失败：{e}")

    teams = [t for t in team_list if t.get("organization") in SCHOOLS]
    if not teams:
        await start_monitor.finish(f"{base_url.split('/')[-1]} 中没有指定学校队伍")

    # 创建全局记录（内存 + 文件）
    meta = {
        "comp_name": base_url.split("/")[-1],
        "run_url": f"{base_url}/run.json",
        "team_ids": [t["id"] for t in teams],
        "id_to_name": {t["id"]: t["name"] for t in teams},
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

# ==============================================================================
# 七、后台轮询线程 —— 只推 TARGET_GROUPS
# ==============================================================================
def monitor_loop(base_url: str):
    logger.info(f"监控线程已启动，比赛 {base_url}")
    while base_url in memory:
        meta = memory[base_url]
        try:
            resp = requests.get(meta["run_url"], timeout=5, headers={"User-Agent": "Mozilla/5.0"})
            runs = resp.json()
        except Exception as e:
            logger.warning(f"获取 run.json 失败：{e}")
            time.sleep(5)
            continue

        # # ==========  当前「仅 AC」逻辑（保持原样）  ==========
        # now_solved = {r["team_id"] for r in runs
        #               if r["team_id"] in meta["team_ids"] and r["status"] == "AC"}
        # new_solved = now_solved - set(meta["already_solved"])
        # if new_solved:
        #     for gid in TARGET_GROUPS:
        #         for tid in new_solved:
        #             name = meta["id_to_name"][tid]
        #             # 原样输出
        #             msg = f"[{meta['comp_name']}] 队伍 {name} 已 AC 题！🎉"
        #             asyncio.create_task(send_ac_msg(int(gid), msg))
        # meta["already_solved"] = list(now_solved)
        # ==========  仅 AC 结束  ==========


        # ------------------------------------------------------------------
        #  下面整块是「任意状态 + 题号」通用版，目前被注释，可随时取消注释
        #  同时把上面「仅 AC」块注释掉即可切换
        # ------------------------------------------------------------------
        from collections import defaultdict
        # 先一次性把大写题号表拉出来（只需一次）
        if 'prob2char' not in meta:
            prob_resp = requests.get(f"{base_url}/run.json", timeout=5)
            prob_resp.raise_for_status()
            # run.json 里假设 {"data":[{"id":1,"short_name":"A"}, ...]}
            meta['prob2char'] = {p['id']: p['short_name']  # 1→A
                                 for p in prob_resp.json()['data']}

        # 取任意新提交（按 run.id 判重）
        seen = set(meta.get("seen_ids", []))
        for run in runs:
            rid = int(run["id"])
            if rid in seen:
                continue
            seen.add(rid)
            # 只关注我们学校
            if run["team_id"] not in meta["team_ids"]:
                continue
            # 题号 1→A，2→B ...
            prob_char = meta['prob2char'][int(run["problem_id"])]
            team_name = meta["id_to_name"][run["team_id"]]
            status = run["status"]          # AC / WRONG_ANSWER / TIME_LIMIT 等
            # 拼装： [赛站] [team] 已 [状态] 了 [题号] 题！
            msg = f"[{meta['comp_name']}] {team_name} 已 {status} 了 {prob_char} 题！"
            for gid in TARGET_GROUPS:
                asyncio.create_task(send_ac_msg(int(gid), msg))
        meta["seen_ids"] = list(seen)
        # ------------------------------------------------------------------


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
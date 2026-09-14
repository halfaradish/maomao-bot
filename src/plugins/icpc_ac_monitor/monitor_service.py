# src/plugins/icpc_ac_monitor/monitor_service.py
"""后台监控线程轮询循环与启动恢复

注意：事件循环缓存在 push._main_event_loop 上，本模块通过模块属性
读写（不能 from-import，否则拿到的是导入瞬间的 None 值）。
"""

import asyncio
import threading
import time

import requests
from nonebot import get_driver, logger

from . import push
from .mappings import _ensure_comp_display
from .standings import (
    _calculate_team_ranks,
    _format_run_duration,
    _is_final_status,
    _pid_to_char,
    _pretty_status,
)
from .state import SCHOOLS, TARGET_GROUPS, conf, memory, save_conf

# -------------------- 轮询推送（固定推全部 TARGET_GROUPS） --------------------
def monitor_loop(base_url: str):
    logger.info(f"监控线程已启动，比赛 {base_url}")

    # 获取主事件循环
    loop = push._main_event_loop
    if not loop or not loop.is_running():
        try:
            driver = get_driver()
            loop = getattr(driver, '_loop', None) or getattr(driver, 'loop', None)
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

        # 初始化 pending_runs，用于跟踪 PENDING 状态的提交
        if "pending_runs" not in meta:
            meta["pending_runs"] = {}

        seen = set(meta["seen_ids"])
        seen_count_before = len(seen)
        pending_runs = meta["pending_runs"]  # rid -> run_data 的映射

        # 实时获取 team.json 确保总数准确，并识别正式队伍（排除打星队伍）
        official_team_ids = None
        all_team_ids_set = None
        try:
            team_resp = requests.get(f"{base_url}/team.json", timeout=5, headers={"User-Agent": "Mozilla/5.0"})
            team_data = team_resp.json()
            if isinstance(team_data, list):
                all_teams = team_data
            elif isinstance(team_data, dict):
                all_teams = list(team_data.values())
            else:
                all_teams = []

            # 构建所有队伍ID集合（包括打星队伍）
            all_team_ids_set = set()
            for team in all_teams:
                tid_raw = team.get("id") or team.get("team_id")
                if tid_raw is not None:
                    all_team_ids_set.add(str(tid_raw))

            # 识别正式队伍：排除打星队伍
            # 打星队伍在 group 字段中标识（如 "star" 等）
            official_team_ids = set()
            star_team_count = 0
            for team in all_teams:
                tid_raw = team.get("id") or team.get("team_id")
                if tid_raw is None:
                    continue
                tid = str(tid_raw)

                # 通过 group 字段判断是否为打星队伍
                # group 是一个数组，如 ["official"] 或 ["unofficial"]
                group = team.get("group", [])
                if isinstance(group, list):
                    # 如果 group 数组包含 "unofficial"，则为打星队伍，排除
                    if "unofficial" in group:
                        star_team_count += 1
                        continue
                elif isinstance(group, str):
                    # 兼容字符串格式
                    group_lower = group.lower()
                    if "unofficial" in group_lower or "star" in group_lower or group == "*":
                        star_team_count += 1
                        continue

                official_team_ids.add(tid)

            actual_total = len(official_team_ids) if official_team_ids else len(all_teams)
            # 只在第一次获取时输出统计信息，避免日志刷屏
            if "team_stats_logged" not in meta:
                logger.info(f"队伍统计：总队伍数={len(all_teams)}, 正式队伍数={actual_total}, 打星队伍数={star_team_count}")
                meta["team_stats_logged"] = True
        except Exception as e:
            logger.warning(f"获取 team.json 失败，使用缓存总数：{e}")
            actual_total = len(meta["team_ids"])
            official_team_ids = None
            all_team_ids_set = {str(tid) for tid in meta["team_ids"]}

        # 使用实时获取的所有队伍ID，如果没有则使用缓存的
        team_ids_set = all_team_ids_set if all_team_ids_set is not None else {str(tid) for tid in meta["team_ids"]}
        watched_ids_set = {str(tid) for tid in meta.get("watched_ids", meta["team_ids"])}

        total_runs = len(runs)
        new_submissions = 0

        rank_map, ordered_teams = _calculate_team_ranks(runs, team_ids_set, actual_total, official_team_ids)

        for run in runs:
            # 先过滤不是我们学校的队伍
            run_team_id = str(run.get("team_id", ""))
            if run_team_id not in watched_ids_set:
                continue

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

            # 获取原始状态（未美化）
            raw_status = str(run.get("status", "UNKNOWN")).upper()
            is_final = _is_final_status(raw_status)

            # 检查是否已经在 pending_runs 中跟踪
            if rid in pending_runs:
                # 如果状态变成最终状态，发送消息并移除跟踪
                if is_final:
                    logger.info(f"提交 {rid} 状态已更新为最终状态：{raw_status}，发送消息")
                    # 使用最新的 run 数据
                    pending_runs.pop(rid)
                    # 继续处理，发送消息
                else:
                    # 仍然是 PENDING 状态，继续跟踪，不发送
                    logger.debug(f"提交 {rid} 仍为 PENDING 状态：{raw_status}，继续跟踪")
                    continue

            # 如果是 PENDING 状态且不在 pending_runs 中，加入跟踪但不发送
            if not is_final:
                logger.info(f"检测到 PENDING 状态提交 {rid}，加入跟踪队列，状态：{raw_status}")
                # 保存 run 的副本用于后续跟踪
                pending_runs[rid] = {
                    "team_id": run_team_id,
                    "problem_id": run.get("problem_id"),
                    "timestamp": run.get("timestamp") or run.get("time") or run.get("submission_time") or run.get("submitted_at"),
                    "status": raw_status,
                }
                # 不加入 seen，不发送消息
                continue

            # 最终状态的提交，正常处理
            seen.add(rid)

            # problem_id 转 A/B/C...
            prob_char = _pid_to_char(run.get("problem_id", -1))

            team_name = meta["id_to_name"].get(run_team_id, "未知队伍")
            status = _pretty_status(run.get("status", "UNKNOWN"))

            timestamp = run.get("timestamp")
            if timestamp is None:
                timestamp = run.get("time") or run.get("submission_time") or run.get("submitted_at")

            duration_str = _format_run_duration(timestamp)

            school_name = meta.get("id_to_school", {}).get(run_team_id, SCHOOLS[0] if SCHOOLS else "未知")
            rank_info = rank_map.get(run_team_id)
            rank_line = f"\n[排名]：{rank_info['rank']}/{rank_info['total']}" if rank_info else ""

            msg = (
                f"[时间]：{duration_str}\n"
                f"[赛站]：{_ensure_comp_display(meta)}\n"
                f"[学校]：{school_name}\n"
                f"[队伍名]：{team_name}\n"
                f"[题号]：{prob_char}\n"
                f"[状态]：{status}"
                f"{rank_line}"
            )
            logger.info(f"检测到新提交：{msg}")

            # 线程安全推送给所有目标群
            for gid in TARGET_GROUPS:
                try:
                    if not loop or not loop.is_running():
                        logger.error(f"事件循环不可用，无法推送消息到群 {gid}")
                        continue

                    future = asyncio.run_coroutine_threadsafe(
                        push.send_ac_msg(int(gid), push._build_push_message(msg, int(gid))), loop
                    )
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
            # 创建干净的配置副本，移除不能序列化的对象（如Thread）和临时跟踪数据（pending_runs）
            clean_memory = {}
            for url, m in memory.items():
                clean_meta = {k: v for k, v in m.items() if k not in ("thread", "pending_runs")}
                clean_memory[url] = clean_meta

            conf["monitors"] = clean_memory
            save_conf(conf)

        if new_submissions > 0:
            logger.info(f"本轮检测到 {new_submissions} 个新提交，已推送到 {len(TARGET_GROUPS)} 个群")

        time.sleep(5)


# ==============================================================================
# 启动时恢复持久化监控
# ==============================================================================
def restore_on_startup():
    """
    bot 启动时遍历 memory，为每个比赛重新启动后台线程。
    """
    # 尝试设置主事件循环（如果还没有设置）
    if push._main_event_loop is None:
        push._main_event_loop = push._get_main_loop()

    if not memory:
        logger.info("icpc_ac_monitor: 没有需要恢复的监控任务")
        return

    if not TARGET_GROUPS:
        logger.warning("icpc_ac_monitor: TARGET_GROUPS 为空，已恢复的监控将无法推送消息")

    for url, meta in list(memory.items()):      # list 防止迭代时修改
        # 确保 team_ids 中的 ID 都是字符串类型（兼容旧配置）
        if "team_ids" in meta:
            meta["team_ids"] = [str(tid) for tid in meta["team_ids"]]
        if "watched_ids" in meta:
            meta["watched_ids"] = [str(tid) for tid in meta["watched_ids"]]
        else:
            meta["watched_ids"] = meta.get("team_ids", [])
        # 确保 id_to_name 的 key 都是字符串
        if "id_to_name" in meta:
            meta["id_to_name"] = {str(k): v for k, v in meta["id_to_name"].items()}
        if "id_to_school" in meta:
            meta["id_to_school"] = {str(k): v for k, v in meta["id_to_school"].items()}
        else:
            meta["id_to_school"] = {}
        _ensure_comp_display(meta)

        thread = threading.Thread(target=monitor_loop, args=(url,), daemon=True)
        meta["thread"] = thread
        thread.start()
        # 显示更清晰的信息：显示原始URL（如果可能）和数据URL
        display_url = url.replace("https://cdn.xcpcio.com/data", "https://board.xcpcio.com")
        logger.info(f"[持久化] 比赛 {_ensure_comp_display(meta)} 已恢复（{display_url}），将推送给 {len(TARGET_GROUPS)} 个目标群")

# 使用启动钩子来恢复监控（此时事件循环已运行）
@get_driver().on_startup
async def startup_restore():
    """在 bot 启动时恢复监控任务"""
    push._main_event_loop = push._get_main_loop()
    restore_on_startup()

# src/plugins/icpc_ac_monitor/standings.py
"""状态常量与排名/时长格式化纯函数（无副作用）"""

from typing import Any, Dict, List, Optional, Tuple

STATUS_MAP = {
    "CORRECT": "✅ AC",
    "AC": "✅ AC",
    "ACCEPTED": "✅ AC",
    "WRONG_ANSWER": "❌ WA",
    "WRONGANSWER": "❌ WA",
    "TIME_LIMIT_EXCEEDED": "⏰ TLE",
    "TIME_LIMIT": "⏰ TLE",
    "RUNTIME_ERROR": "💥 RE",
    "COMPILATION_ERROR": "🛠 CE",
}


def _pretty_status(raw: str) -> str:
    upper = (raw or "").upper()
    return STATUS_MAP.get(upper, upper or "UNKNOWN")

# 计入罚时的错误状态（只对这些状态 +20 分钟），避免把 PENDING/JUDGING 之类算作罚时
WRONG_STATUSES = {
    "WRONG_ANSWER",
    "WRONGANSWER",
    "WA",
    "TIME_LIMIT_EXCEEDED",
    "TLE",
    "RUNTIME_ERROR",
    "RUNTIME ERROR",
    "RE",
    "MEMORY_LIMIT_EXCEEDED",
    "MLE",
    "OUTPUT_LIMIT_EXCEEDED",
    "OLE",
    "PRESENTATION_ERROR",
    "PE",
}


ACCEPT_STATUSES = {"CORRECT", "ACCEPTED", "AC", "YES"}

# 未完成状态（需要等待最终结果）
PENDING_STATUSES = {
    "PENDING",
    "JUDGING",
    "RUNNING",
    "IN_QUEUE",
    "WAITING",
    "COMPILING",
    "TESTING",
}

def _is_final_status(status: str) -> bool:
    """判断状态是否为最终状态（非 PENDING/JUDGING 等）"""
    if not status:
        return False
    upper = status.upper()
    # 如果不在未完成状态集合中，则认为是最终状态
    return upper not in PENDING_STATUSES


def _format_run_duration(timestamp: Any) -> str:
    """将 run.json 内的毫秒时间戳转换为 2h29min 样式"""
    if timestamp is None:
        return "未知"
    try:
        value = float(timestamp)
    except Exception:
        return "未知"

    # timestamp 默认是毫秒，直接除以1000转换为秒
    seconds = int(value / 1000)
    if seconds < 0:
        return "未知"

    hours, remainder = divmod(seconds, 3600)
    minutes, secs = divmod(remainder, 60)
    parts = []
    if hours:
        parts.append(f"{hours}h")
    if minutes:
        parts.append(f"{minutes}min")
    if not hours and not minutes:
        parts.append(f"{secs}s")
    return "".join(parts) or "0s"


def _extract_run_seconds(run: Dict[str, Any]) -> Optional[float]:
    """从 run.json 中提取提交时间（秒），timestamp 默认是毫秒，直接除以1000"""
    for key in ("timestamp", "time", "submission_time", "submitted_at"):
        value = run.get(key)
        if value is None or value == "":
            continue
        try:
            num = float(value)
            # timestamp 默认是毫秒，直接除以1000转换为秒
            return num / 1000.0
        except Exception:
            continue
    return None


def _calculate_team_ranks(
    runs: List[Dict[str, Any]], team_ids_set: set, all_team_total: int, official_team_ids: Optional[set] = None
) -> Tuple[Dict[str, Dict[str, Any]], List[tuple]]:
    """根据 run.json 计算正式队伍的排名（排除打星队伍）"""
    # 如果提供了正式队伍列表，只计算正式队伍；否则计算所有队伍
    if official_team_ids is not None:
        # 直接使用正式队伍列表（已经排除了打星队伍）
        valid_team_ids = official_team_ids
    else:
        valid_team_ids = team_ids_set

    # 初始化所有正式队伍（包括没有提交的）
    team_stats: Dict[str, Dict[str, Any]] = {
        tid: {
            "solved": 0,
            "penalty": 0,
            "first_ac_time": None,  # 首次 AC 时间
            "last_ac_time": None,   # 最后一题 AC 时间
            "problems": {},
            "has_submission": False
        }
        for tid in valid_team_ids
    }

    # 收集所有在 run.json 中出现的队伍ID
    teams_with_runs = set()

    sorted_runs = sorted(runs, key=lambda r: _extract_run_seconds(r) or float("inf"))

    for run in sorted_runs:
        tid = str(run.get("team_id", ""))
        # 只处理正式队伍
        if tid not in valid_team_ids:
            continue
        teams_with_runs.add(tid)
        pid = str(run.get("problem_id", ""))
        if pid == "":
            continue
        sec = _extract_run_seconds(run)
        if sec is None:
            continue
        status = str(run.get("status", "")).upper()
        problems = team_stats[tid]["problems"]
        state = problems.setdefault(pid, {"solved": False, "wrong": 0, "first_ac_sec": None})
        if state["solved"]:
            continue
        if status in ACCEPT_STATUSES:
            state["solved"] = True
            team_stats[tid]["solved"] += 1
            # 罚时 = AC时间（分钟）+ 错误次数 × 20分钟
            penalty_minutes = int(sec // 60)
            team_stats[tid]["penalty"] += penalty_minutes + state["wrong"] * 20
            # 记录首次AC时间（用于相同成绩时的排序）
            if state["first_ac_sec"] is None:
                state["first_ac_sec"] = sec
            if team_stats[tid]["first_ac_time"] is None or sec < team_stats[tid]["first_ac_time"]:
                team_stats[tid]["first_ac_time"] = sec
            if team_stats[tid]["last_ac_time"] is None or sec > team_stats[tid]["last_ac_time"]:
                team_stats[tid]["last_ac_time"] = sec
            team_stats[tid]["has_submission"] = True
        else:
            # 只有明确的错误提交才算一次罚时
            if status in WRONG_STATUSES:
                state["wrong"] += 1
                team_stats[tid]["has_submission"] = True

    # 排序：有提交的队伍按AC数、罚时、首次AC时间排序；无提交的队伍排在最后
    # ICPC规则：1. AC数多的在前 2. 罚时少的在前 3. 首次AC时间早的在前
    ordered = sorted(
        (
            (
                tid,
                data["solved"],
                data["penalty"],
                data["last_ac_time"] if data["last_ac_time"] is not None else float("inf"),
                data["has_submission"],
                int(tid) if tid.isdigit() else 0,  # 用于无提交队伍的排序
            )
            for tid, data in team_stats.items()
        ),
        key=lambda x: (
            not x[4],  # 有提交的排在前面（False < True，所以 not x[4] 让 True 在前）
            -x[1],     # AC数降序
            x[2],      # 罚时升序
            x[3],      # 最后一题 AC 时间升序
            x[5],      # 无提交队伍按ID排序
        ),
    )

    # 总数使用传入的 all_team_total（已经排除了打星队伍）
    total = all_team_total
    rank_map: Dict[str, Dict[str, Any]] = {}
    for idx, (tid, solved, penalty, first_time, has_sub, _) in enumerate(ordered, start=1):
        rank_map[tid] = {
            "rank": idx,
            "total": total,
            "solved": solved,
            "penalty": penalty,
        }
    return rank_map, ordered


def _to_base_url(url: str) -> str:
    """将 board 域名转换为 cdn 数据域名"""
    return url.rstrip("/").replace("https://board.xcpcio.com", "https://cdn.xcpcio.com/data")


def _pid_to_char(pid) -> str:
    """0 -> A, 1 -> B ... 超出则返回数字形式或?"""
    try:
        n = int(pid)
        if 0 <= n < 26:
            return chr(ord("A") + n)
        return str(pid)
    except (ValueError, TypeError):
        return "?"

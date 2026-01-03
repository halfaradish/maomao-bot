# src/plugins/icpc_ac_monitor/icpc_ac_monitor.py
"""
ICPC AC Monitor Plugin  ‑  单文件全局版
1. data/icpc_ac_monitor.json 同时存目标群、学校、监控比赛
2. 本地可手动改群号/学校，代码只读写 monitors 部分
3. 开始/取消都是全局开关，所有目标群同步收 AC 推送
"""

import json
import os
import re
import tempfile
import threading
import time
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple, Union
import asyncio
import requests

from nonebot import get_bot, get_driver, logger, on_command
from nonebot.adapters.onebot.v11 import Bot, Event, Message, MessageSegment
from nonebot.params import CommandArg

# ==============================================================================
# 一、路径相关
# ==============================================================================
# 计算项目根目录：插件文件向上 4 级就是项目根
BASE_DIR = Path(__file__).resolve().parent.parent.parent.parent
# 单文件配置路径：data/icpc_ac_monitor.json
CONF_FILE = BASE_DIR / "data" / "icpc_ac_monitor.json"
# 城市拼音映射文件，用于将赛站拼音转换为中文
CITY_MAP_FILE = BASE_DIR / "data" / "city_pinyin_map.json"
# 学校名称映射文件，用于支持中英文名称匹配
SCHOOL_MAP_FILE = BASE_DIR / "data" / "school_name_map.json"
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
        tpl = {"target_groups": [], "schools": ["广西大学"], "monitors": {}, "at_whitelist": []}
        save_conf(tpl)
        return tpl
    try:
        with CONF_FILE.open("r", encoding="utf-8") as f:
            data = json.load(f)
            data.setdefault("target_groups", [])
            data.setdefault("schools", [])
            data.setdefault("monitors", {})
            data.setdefault("at_whitelist", [])
            return data
    except Exception as e:
        logger.warning(f"读取配置失败：{e}，返回空模板")
        return {"target_groups": [], "schools": [], "monitors": {}, "at_whitelist": []}

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


def _load_city_mapping() -> Tuple[Dict[str, str], Dict[str, str]]:
    """加载 data/city_pinyin_map.json，返回中文->拼音、拼音->中文双向映射"""
    if not CITY_MAP_FILE.exists():
        logger.warning(f"未在 {CITY_MAP_FILE} 找到城市映射，赛站将保持原始拼音显示。")
        return {}, {}
    try:
        with CITY_MAP_FILE.open("r", encoding="utf-8") as f:
            data = json.load(f)
        if not isinstance(data, dict):
            raise ValueError("city_pinyin_map.json 内容不是字典。")
        forward = {}
        for zh, py in data.items():
            zh_name = str(zh).strip()
            py_slug = str(py).strip().lower()
            if not zh_name or not py_slug:
                continue
            forward[zh_name] = py_slug
        reverse = {py_slug: zh_name for zh_name, py_slug in forward.items()}
        return forward, reverse
    except Exception as e:
        logger.warning(f"加载城市映射失败：{e}")
        return {}, {}


CITY_TO_PINYIN, PINYIN_TO_CITY = _load_city_mapping()


def _load_school_mapping() -> Dict[str, List[str]]:
    """加载 data/school_name_map.json，返回中文名称->英文名称列表的映射"""
    if not SCHOOL_MAP_FILE.exists():
        logger.info(f"未在 {SCHOOL_MAP_FILE} 找到学校名称映射，将使用精确匹配。")
        return {}
    try:
        with SCHOOL_MAP_FILE.open("r", encoding="utf-8") as f:
            data = json.load(f)
        if not isinstance(data, dict):
            raise ValueError("school_name_map.json 内容不是字典。")
        result = {}
        for zh_name, aliases in data.items():
            zh_name = str(zh_name).strip()
            if not zh_name:
                continue
            # 支持字符串或列表格式
            if isinstance(aliases, str):
                alias_list = [aliases.strip()]
            elif isinstance(aliases, list):
                alias_list = [str(a).strip() for a in aliases if a]
            else:
                continue
            if alias_list:
                result[zh_name] = alias_list
        return result
    except Exception as e:
        logger.warning(f"加载学校名称映射失败：{e}")
        return {}


SCHOOL_NAME_MAP = _load_school_mapping()


def _is_school_match(organization: str, schools: List[str], school_map: Dict[str, List[str]]) -> bool:
    """
    检查 organization 是否匹配 schools 列表中的任一学校名称
    支持精确匹配和映射匹配（中英文名称映射）
    """
    if not organization:
        return False
    org = organization.strip()
    
    # 1. 精确匹配：直接检查 organization 是否在配置的学校列表中
    if org in schools:
        return True
    
    # 2. 映射匹配：检查 organization 是否匹配配置学校名称的英文别名
    for school in schools:
        aliases = school_map.get(school, [])
        if org in aliases:
            return True
    
    return False


def _resolve_city_display_name(raw: str) -> str:
    """将 URL 中的赛站拼音转换为中文名称"""
    if not raw:
        return raw
    slug = raw.lower()
    if slug in PINYIN_TO_CITY:
        return PINYIN_TO_CITY[slug]
    # 分割出可能的拼音片段（去掉数字、破折号等）
    tokens = [tok for tok in re.split(r"[^a-z]+", slug) if tok]
    for token in tokens:
        if token in PINYIN_TO_CITY:
            return PINYIN_TO_CITY[token]
    return raw


def _ensure_comp_display(meta: Dict[str, Any]) -> str:
    """保证 meta 中存在中文赛站名，并返回它"""
    if not isinstance(meta, dict):
        return ""
    display = meta.get("comp_display_name")
    if display:
        return display
    raw = meta.get("comp_name", "")
    display = _resolve_city_display_name(raw)
    meta["comp_display_name"] = display
    return display
# 可被艾特提醒的 QQ 白名单（qq -> 所属群id，None表示全局）
def _normalize_whitelist(raw: Any) -> Dict[int, Optional[int]]:
    result: Dict[int, Optional[int]] = {}
    if isinstance(raw, dict):
        for k, v in raw.items():
            try:
                qq = int(k)
            except Exception:
                continue
            group_id = None
            if isinstance(v, dict):
                group_id = v.get("group_id")
            elif isinstance(v, int):
                group_id = v
            elif v is None:
                group_id = None
            elif isinstance(v, str) and v.isdigit():
                group_id = int(v)
            result[qq] = int(group_id) if isinstance(group_id, int) else None
        return result
    if isinstance(raw, list):
        for item in raw:
            if isinstance(item, dict):
                qq = item.get("qq")
                group_id = item.get("group_id")
            else:
                qq = item
                group_id = None
            try:
                qq_int = int(qq)
            except Exception:
                continue
            try:
                gid_int = int(group_id)
            except Exception:
                gid_int = None
            result[qq_int] = gid_int
    elif raw and isinstance(raw, (int, str)):
        try:
            result[int(raw)] = None
        except Exception:
            pass
    return result


AT_WHITELIST: Dict[int, Optional[int]] = _normalize_whitelist(conf.get("at_whitelist", []))
# 正在全局监控的比赛字典（url 为 key）
memory: Dict[str, Any] = conf["monitors"]

# ==============================================================================
# 四、命令注册
# ==============================================================================
start_monitor = on_command("开始监控", aliases={"monitor"}, priority=5)
stop_monitor = on_command("取消监控", aliases={"stop"}, priority=5)
add_at_whitelist = on_command(
    "添加监控", aliases={"添加监控名单", "添加监控指令", "添加监控艾特", "添加监控提醒", "添加ac艾特"}, priority=5, block=True
)
remove_at_whitelist = on_command(
    "移除监控", aliases={"移除监控艾特", "删除监控艾特", "删除ac艾特"}, priority=5, block=True
)
list_at_whitelist = on_command(
    "查看监控名单", aliases={"查看监控艾特", "查看ac艾特", "ac艾特名单"}, priority=5, block=True
)
monitor_help = on_command("监控", priority=5, block=True)
logger.info("icpc_ac_monitor 插件加载完成（单文件全局版）")

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

def _format_timestamp(timestamp: Any, contest_start_timestamp: Optional[float] = None) -> str:
    """将时间戳转换为可读的时间格式"""
    if timestamp is None or contest_start_timestamp is None:
        return ""
    
    try:
        # 转换为数字
        if isinstance(timestamp, str):
            timestamp = float(timestamp)
        
        # timestamp 是毫秒数，除以1000转换为秒
        relative_seconds = timestamp / 1000.0
        if relative_seconds < 0:
            return ""
        
        # 开始时间戳可能是秒或毫秒，需要判断
        start_ts = float(contest_start_timestamp)
        if start_ts > 1e10:  # 毫秒时间戳（13位）
            start_ts = start_ts / 1000.0
        
        # 实际时间 = 开始时间戳 + 相对时间
        actual_timestamp = start_ts + relative_seconds
        actual_dt = datetime.fromtimestamp(actual_timestamp)
        return actual_dt.strftime("%H:%M:%S")
    except Exception as e:
        logger.warning(f"时间戳格式化失败：timestamp={timestamp}, start_timestamp={contest_start_timestamp}, 错误：{e}")
        return ""


def _calc_relative_seconds(timestamp: Any, contest_start_timestamp: Optional[float]) -> Optional[float]:
    if timestamp is None or contest_start_timestamp is None:
        return None
    try:
        ts = float(timestamp)
        if ts > 1e12:
            ts /= 1000.0
        start_ts = float(contest_start_timestamp)
        if start_ts > 1e12:
            start_ts /= 1000.0
        relative = ts - start_ts
        return relative if relative >= 0 else None
    except Exception:
        return None

# ==============================================================================
# 五、艾特白名单管理
# ==============================================================================
try:
    SUPERUSERS: set[str] = {str(u) for u in get_driver().config.superusers}
except Exception:
    SUPERUSERS = set()


def _is_authorized(event: Event) -> bool:
    """SUPERUSER 或白名单成员才可管理"""
    user_id = getattr(event, "user_id", None)
    if user_id is None:
        return False
    if str(user_id) in SUPERUSERS:
        return True
    try:
        uid = int(user_id)
    except Exception:
        return False
    return uid in AT_WHITELIST


def _serialize_whitelist() -> List[Dict[str, Optional[int]]]:
    return [{"qq": qq, "group_id": gid} for qq, gid in AT_WHITELIST.items()]


def _persist_at_whitelist():
    """落盘艾特白名单"""
    conf["at_whitelist"] = _serialize_whitelist()
    save_conf(conf)


def _parse_qq_numbers(text: str) -> List[int]:
    """将输入文本解析为 QQ 号列表"""
    tokens = re.split(r"[\s,，]+", text.strip())
    qq_list = []
    for token in tokens:
        if not token:
            continue
        if not token.isdigit():
            raise ValueError(f"非法 QQ 号：{token}")
        qq_list.append(int(token))
    if not qq_list:
        raise ValueError("未解析到任何 QQ 号")
    return qq_list


def _extract_mentions(message: Message) -> List[int]:
    """从命令参数中解析 @ 的 QQ"""
    mentions: List[int] = []
    for seg in message:
        if seg.type != "at":
            continue
        qq = seg.data.get("qq")
        if not qq or qq == "all" or not str(qq).isdigit():
            continue
        mentions.append(int(qq))
    return mentions


@add_at_whitelist.handle()
async def handle_add_at(event: Event, args: Message = CommandArg()):
    if not _is_authorized(event):
        await add_at_whitelist.finish("只有白名单成员或管理员可执行此命令。")
    text = args.extract_plain_text().strip()
    mention_qqs = _extract_mentions(args)
    group_id = getattr(event, "group_id", None)

    parsed_numbers: List[int] = []
    if text:
        try:
            parsed_numbers = _parse_qq_numbers(text)
        except ValueError as e:
            await add_at_whitelist.finish(str(e))

    qqs = mention_qqs + parsed_numbers
    if not qqs:
        await add_at_whitelist.finish("请在命令后提供要添加的 QQ 号，可直接输入或 @ 指定。")

    added = []
    for qq in qqs:
        previous = AT_WHITELIST.get(qq)
        if previous == group_id:
            continue
        AT_WHITELIST[qq] = group_id if group_id is not None else None
        added.append(qq)
    if added:
        _persist_at_whitelist()
        msg = f"成功添加 {len(added)} 个 QQ 到艾特白名单：" + ", ".join(map(str, added))
    else:
        msg = "全部 QQ 已存在于白名单。"
    await add_at_whitelist.finish(msg)


@remove_at_whitelist.handle()
async def handle_remove_at(event: Event, args: Message = CommandArg()):
    if not _is_authorized(event):
        await remove_at_whitelist.finish("只有白名单成员或管理员可执行此命令。")
    text = args.extract_plain_text().strip()
    mention_qqs = _extract_mentions(args)

    parsed_numbers: List[int] = []
    if text:
        try:
            parsed_numbers = _parse_qq_numbers(text)
        except ValueError as e:
            await remove_at_whitelist.finish(str(e))

    qqs = mention_qqs + parsed_numbers
    if not qqs:
        await remove_at_whitelist.finish("请在命令后提供要移除的 QQ 号，可直接输入或 @ 指定。")

    removed = []
    for qq in qqs:
        if qq in AT_WHITELIST:
            AT_WHITELIST.pop(qq, None)
            removed.append(qq)
    if removed:
        _persist_at_whitelist()
        msg = f"已从艾特白名单移除 {len(removed)} 个 QQ：" + ", ".join(map(str, removed))
    else:
        msg = "这些 QQ 不在白名单中。"
    await remove_at_whitelist.finish(msg)


async def _resolve_display_name(bot: Bot, qq: int, group_id: Optional[int]) -> str:
    """优先返回群名片，其次昵称"""
    if group_id:
        try:
            info = await bot.get_group_member_info(group_id=group_id, user_id=qq, no_cache=True)
            card = (info.get("card") or "").strip()
            nickname = (info.get("nickname") or "").strip()
            if card:
                return card
            if nickname:
                return nickname
        except Exception as e:
            logger.debug(f"获取群成员信息失败：qq={qq}, group={group_id}, err={e}")
    try:
        info = await bot.get_stranger_info(user_id=qq, no_cache=True)
        nickname = (info.get("nickname") or "").strip()
        if nickname:
            return nickname
    except Exception as e:
        logger.debug(f"获取陌生人信息失败：qq={qq}, err={e}")
    return str(qq)


async def _resolve_group_name(bot: Bot, group_id: Optional[int]) -> str:
    if group_id is None:
        return "所有群"
    try:
        info = await bot.get_group_info(group_id=group_id, no_cache=True)
        name = info.get("group_name")
        if name:
            return name
    except Exception as e:
        logger.debug(f"获取群信息失败：group_id={group_id}, err={e}")
    return str(group_id)


@list_at_whitelist.handle()
async def handle_list_at(bot: Bot, event: Event):
    if not _is_authorized(event):
        await list_at_whitelist.finish("只有白名单成员或管理员可执行此命令。")
    if not AT_WHITELIST:
        await list_at_whitelist.finish("当前艾特白名单为空，可使用『添加监控』命令添加。")

    group_id = getattr(event, "group_id", None)
    lines = []
    for qq, bind_group in AT_WHITELIST.items():
        display = await _resolve_display_name(bot, qq, group_id)
        group_label = await _resolve_group_name(bot, bind_group)
        lines.append(f"{display} - {qq}（{group_label}）")

    await list_at_whitelist.finish("当前艾特白名单：\n" + "\n".join(lines))


@monitor_help.handle()
async def handle_monitor_help():
    msg = (
        "监控指令一览：\n"
        "1. 开始监控 <比赛URL>\n"
        "2. 取消监控 <比赛URL>\n"
        "3. 添加监控 <QQ/@成员>\n"
        "4. 移除监控 <QQ/@成员>\n"
        "5. 查看监控名单"
    )
    await monitor_help.finish(msg)

# ==============================================================================
# 六、开始监控 —— 全局开关
# ==============================================================================
@start_monitor.handle()
async def handle_start_monitor(bot: Bot, event: Event, args: Message = CommandArg()):
    """开始监控比赛"""
    set_bot_instance(bot)
    url = args.extract_plain_text().strip()
    if not url or not url.startswith("https://board.xcpcio.com"):
        await start_monitor.finish(
            "请输入正确比赛网址，例如：\n开始监控 https://board.xcpcio.com/icpc/50th/shenyang"
        )
    base_url = _to_base_url(url)

    # 全局重复判断
    if base_url in memory:
        await start_monitor.finish("该比赛已在监控列表中，无需重复添加。")

    # 获取比赛配置信息（包含开始时间戳）
    contest_start_timestamp = None
    try:
        # 尝试读取 config.json
        config_resp = requests.get(f"{base_url}/config.json", timeout=5, headers={"User-Agent": "Mozilla/5.0"})
        config_data = config_resp.json()
        contest_start_timestamp = config_data.get("start_time")
        if contest_start_timestamp:
            logger.info(f"读取到比赛开始时间戳：{contest_start_timestamp}")
    except Exception as e:
        # 如果 config.json 不存在，尝试 contest.json
        try:
            contest_resp = requests.get(f"{base_url}/contest.json", timeout=5, headers={"User-Agent": "Mozilla/5.0"})
            contest_data = contest_resp.json()
            contest_start_timestamp = contest_data.get("start_time")
            if contest_start_timestamp:
                logger.info(f"从 contest.json 读取到比赛开始时间戳：{contest_start_timestamp}")
        except Exception:
            logger.warning(f"获取比赛配置失败：{e}")

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

    watched_teams = [t for t in team_list if _is_school_match(t.get("organization", ""), SCHOOLS, SCHOOL_NAME_MAP)]
    if not watched_teams:
        await start_monitor.finish(f"{base_url.split('/')[-1]} 中没有指定学校队伍")

    team_ids_list = []
    watched_ids = []
    id_to_name_dict = {}
    id_to_school_dict = {}
    for t in team_list:
        tid_raw = t.get("id") or t.get("team_id")
        tid = str(tid_raw) if tid_raw is not None else ""
        team_ids_list.append(tid)
        id_to_name_dict[tid] = t.get("name", "未知队伍")
        id_to_school_dict[tid] = t.get("organization", "未知")
        if _is_school_match(t.get("organization", ""), SCHOOLS, SCHOOL_NAME_MAP):
            watched_ids.append(tid)
    
    comp_slug = base_url.split("/")[-1]
    meta = {
        "comp_name": comp_slug,
        "comp_display_name": _resolve_city_display_name(comp_slug),
        "run_url": f"{base_url}/run.json",
        "team_ids": team_ids_list,
        "watched_ids": watched_ids,
        "id_to_name": id_to_name_dict,
        "id_to_school": id_to_school_dict,
        "already_solved": [],
        "contest_start_timestamp": contest_start_timestamp,  # 存储比赛开始时间戳（Unix 时间戳）
    }
    logger.info(f"监控配置：队伍数量={len(team_ids_list)}, 目标群={len(TARGET_GROUPS)}个")
    memory[base_url] = meta
    conf["monitors"] = memory
    save_conf(conf)
    await start_monitor.send(f"已添加全局监控：{_ensure_comp_display(meta)}")

    # 启动唯一轮询线程
    thread = threading.Thread(target=monitor_loop, args=(base_url,), daemon=True)
    memory[base_url]["thread"] = thread
    thread.start()

# ==============================================================================
# 六、取消监控 —— 全局关闭
# ==============================================================================
@stop_monitor.handle()
async def handle_stop_monitor(bot: Bot, event: Event, args: Message = CommandArg()):
    """取消监控比赛"""
    url = args.extract_plain_text().strip()
    if not url or not url.startswith("https://board.xcpcio.com"):
        await stop_monitor.finish("请输入要暂停的比赛网址，例如：\n取消监控 https://board.xcpcio.com/icpc/50th/shenyang")
    base_url = _to_base_url(url)

    meta = memory.pop(base_url, None)
    if not meta:
        await stop_monitor.finish("目前没有该比赛的监控～")

    # 立刻落盘
    conf["monitors"] = memory
    save_conf(conf)
    await stop_monitor.finish(f"已完全停止监控：{_ensure_comp_display(meta)}")

# -------------------- 轮询推送（固定推全部 TARGET_GROUPS） --------------------
def monitor_loop(base_url: str):
    logger.info(f"监控线程已启动，比赛 {base_url}")

    # 获取主事件循环
    loop = _main_event_loop
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
                        send_ac_msg(int(gid), _build_push_message(msg, int(gid))), loop
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
# 八、异步发群消息
# ==============================================================================
# 全局变量：存储 bot 实例和主事件循环（在启动时设置）
_cached_bot = None
_main_event_loop = None

def _get_main_loop():
    """获取主事件循环"""
    try:
        return asyncio.get_running_loop()
    except RuntimeError:
        try:
            loop = asyncio.get_event_loop()
            return loop if loop.is_running() else None
        except Exception:
            return None

def set_bot_instance(bot: Bot):
    """在启动时设置 bot 实例和主事件循环"""
    global _cached_bot, _main_event_loop
    _cached_bot = bot
    _main_event_loop = _get_main_loop()

def _build_push_message(content: str, group_id: Optional[int]) -> Message:
    """根据目标群构建带 @ 的消息"""
    mentions = []
    for qq, bind_group in AT_WHITELIST.items():
        if bind_group is None or (group_id is not None and bind_group == group_id):
            mentions.append(str(qq))
    if not mentions:
        return Message(content)
    msg = Message()
    for qq in mentions:
        msg += MessageSegment.at(qq)
        msg += MessageSegment.text(" ")
    msg += MessageSegment.text("\n" + content)
    return msg


async def send_ac_msg(group_id: int, message: Union[str, Message]):
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
        _main_event_loop = _get_main_loop()
    
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
    global _main_event_loop
    _main_event_loop = _get_main_loop()
    restore_on_startup()
# -------------------- 新增指令：赛时过题（按队输出） --------------------
query_status = on_command("赛时过题", aliases={"过题情况"}, priority=5)

def _pid_to_char(pid) -> str:
    """0 -> A, 1 -> B ... 超出则返回数字形式或?"""
    try:
        n = int(pid)
        if 0 <= n < 26:
            return chr(ord("A") + n)
        return str(pid)
    except (ValueError, TypeError):
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
    comp_slug = base_url.split("/")[-1]
    result = {
        "comp_name": _resolve_city_display_name(comp_slug),
        "comp_slug": comp_slug,
        "teams": [],
    }
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
        if _is_school_match(org, schools, SCHOOL_NAME_MAP):
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

    if info.get("comp_name"):
        comp_name = info["comp_name"]
    else:
        comp_name = _resolve_city_display_name(info.get("comp_slug", base_url.split("/")[-1]))
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

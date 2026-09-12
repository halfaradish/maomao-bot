"""插件使用统计 — 查询命令

插件统计 [今天|昨天|本周|本月|总] [全环境] [N]
"""
from datetime import datetime, timedelta

from nonebot import on_command
from nonebot.adapters.onebot.v11 import Message, MessageEvent
from nonebot.params import CommandArg

from . import dao
from .config import plugin_config

RANGE_MAP = {"今天": "today", "昨天": "yesterday", "本周": "week", "本月": "month", "总": "all"}
RANGE_LABELS = {"today": "今天", "yesterday": "昨天", "week": "本周", "month": "本月", "all": "总计"}
CROSS_ENV_KEYWORDS = {"全环境", "跨环境"}

stats_cmd = on_command("插件统计", aliases={"usage", "pluginstat"}, priority=5, block=True)


def _resolve_range_key(tokens: list[str]) -> str:
    for t in tokens:
        if t in RANGE_MAP:
            return RANGE_MAP[t]
    return "week"


def _range_bounds(key: str) -> tuple[datetime, datetime | None]:
    """统计区间的 [start, end)，end 为 None 表示到当前为止"""
    today = datetime.now().date()
    day_start = datetime.combine(today, datetime.min.time())
    if key == "today":
        return day_start, day_start + timedelta(days=1)
    if key == "yesterday":
        return day_start - timedelta(days=1), day_start
    if key == "week":
        return day_start - timedelta(days=today.weekday()), None
    if key == "month":
        return day_start.replace(day=1), None
    return datetime(2000, 1, 1), None


@stats_cmd.handle()
async def _(args: Message = CommandArg()):
    tokens = args.extract_plain_text().split()
    range_key = _resolve_range_key(tokens)
    cross_env = any(t in CROSS_ENV_KEYWORDS for t in tokens)

    top_n = plugin_config.plugin_usage_stats_top_n
    for t in tokens:
        if t.isdigit() and int(t) > 0:
            top_n = int(t)
            break

    start, end = _range_bounds(range_key)
    env_tag = None if cross_env else dao.current_env_tag()
    rows = await dao.query_ranking(start=start, end=end, env_tag=env_tag, limit=top_n)

    env_label = "全环境" if cross_env else dao.current_env_tag()
    header = f"插件使用统计（{RANGE_LABELS[range_key]} · {env_label}）"
    if not rows:
        await stats_cmd.finish(f"{header}\n该时间段内暂无插件使用记录")

    display_names = dao.build_display_names({r.module_name for r in rows})
    lines = [header]
    lines += [f"{i}. {display_names[r.module_name]} {r.use_count}次" for i, r in enumerate(rows, 1)]
    await stats_cmd.finish("\n".join(lines))

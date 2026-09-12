"""这就是VV — 张维为语录表情包插件

检索《这就是中国》节目台词，从远程帧图库截取对应画面发送。
数据源与截帧算法移植自 vv.py 对接原型（github.com/Cicada000/VV）。

管控方式：默认开放 + vv 专属群黑名单（vv:use 权限点，黑名单模式）。
"""
import asyncio
import re

from nonebot import get_driver, get_plugin_config, logger, on_command, on_regex
from nonebot.adapters.onebot.v11 import (
    GroupMessageEvent,
    Message,
    MessageEvent,
    MessageSegment,
)
from nonebot.params import CommandArg
from nonebot.permission import SUPERUSER
from nonebot.plugin import PluginMetadata
from sqlalchemy import delete as sa_delete
from sqlalchemy import select

from src.common.database import async_session_factory
from src.common.model.model import PluginBadgeColor, PluginGroupEnum
from src.common.models.vv_models import VvGroupBlacklist
from src.common.permission import perm_cache

from . import permissions  # noqa: F401
from .config import Config
from .data_source import (
    extract_frame,
    load_bili_mapping,
    load_records,
    parse_episode,
    parse_seconds,
    random_pick,
    search_local,
)

__plugin_meta__ = PluginMetadata(
    name="这就是VV",
    description="张维为语录表情包：检索《这就是中国》节目台词并截取对应画面",
    usage=(
        "随机vv —— 随机来一张 VV 表情包\n"
        "vv说<台词> —— 按台词检索对应画面（如：vv说中国人你要自信）\n"
        "──── 管理命令（仅超级管理员）────\n"
        "vv拉黑 [群号] —— 将群加入黑名单（禁用本插件；在目标群发送可省略群号）\n"
        "vv解拉黑 [群号] —— 将群移出黑名单\n"
        "vv黑名单 —— 查看黑名单列表"
    ),
    config=Config,
    supported_adapters={"~onebot.v11"},
    extra={
        "group": PluginGroupEnum.UTILITY.value,
        "badge_color": PluginBadgeColor.GREEN.value,
        "author": "half",
        "version": "0.1.1",
    },
)

config = get_plugin_config(Config)


# ============================================================
# 命令前缀：on_regex 不经过 COMMAND_START，需自行对齐其语义
# （非空前缀必选；配置含空串时前缀可省略）
# ============================================================
def _build_prefix_pattern(starts) -> str:
    prefixes = sorted((p for p in starts if p), key=len, reverse=True)
    alts = "|".join(re.escape(p) for p in prefixes)
    if not alts:
        return ""
    return f"(?:{alts})?" if "" in starts else f"(?:{alts})"


_PREFIX = _build_prefix_pattern(get_driver().config.command_start)

# ============================================================
# 数据懒加载（43MB 缓存 + B站映射，线程中加载避免阻塞事件循环）
# ============================================================
_records: list | None = None
_records_lock = asyncio.Lock()
_bili_mapping: dict[str, str] | None = None


async def _get_records() -> list:
    global _records
    if _records is None:
        async with _records_lock:
            if _records is None:
                _records = await asyncio.to_thread(load_records)
                logger.info(f"[vv] 字幕缓存加载完成，共 {len(_records)} 条台词")
    return _records


async def _get_bili_mapping() -> dict[str, str]:
    global _bili_mapping
    if _bili_mapping is None:
        _bili_mapping = await asyncio.to_thread(load_bili_mapping)
    return _bili_mapping


# ============================================================
# 黑名单权限点（默认开放，命中即拦截）
# ============================================================
async def is_group_blocked(group_id: int | None) -> bool:
    """vv 专属群黑名单查询；私聊（group_id 为空）恒放行。"""
    if group_id is None:
        return False
    cache_key = f"vv:bl:{group_id}"
    cached = perm_cache.get(cache_key)
    if cached is not None:
        return cached
    async with async_session_factory() as session:
        stmt = select(VvGroupBlacklist.id).where(
            VvGroupBlacklist.group_id == group_id
        ).limit(1)
        blocked = (await session.execute(stmt)).first() is not None
    perm_cache.set(cache_key, blocked)
    return blocked


# ============================================================
# 业务层：截帧并发送结果
# ============================================================
async def send_vv_result(matcher, result: dict) -> None:
    episode = parse_episode(result["filename"])
    seconds = parse_seconds(result["timestamp"])
    if episode is None or seconds is None:
        await matcher.finish("这条记录解析不出画面位置，换一条试试吧")
    try:
        img_bytes = await asyncio.to_thread(extract_frame, episode, seconds)
    except Exception as e:
        logger.error(f"[vv] 截帧失败: {e}")
        await matcher.finish("截帧失败了，稍后再试试吧")

    text = f"\n台词：{result['text']}\n出处：P{episode} @{result['timestamp']}"
    bili_path = (await _get_bili_mapping()).get(result["filename"])
    if bili_path:
        text += f"\nB站：https://www.bilibili.com{bili_path}?t={seconds}"
    await matcher.send(MessageSegment.image(img_bytes) + text)


# ============================================================
# 指令层：随机vv / vv说xxx
# ============================================================
random_vv = on_regex(rf"^{_PREFIX}[随隨][机機]\s*[vVｖＶ]{{1,2}}$", priority=5, block=True)


@random_vv.handle()
async def handle_random_vv(event: MessageEvent):
    if isinstance(event, GroupMessageEvent) and await is_group_blocked(event.group_id):
        logger.info(f"[vv] 群 {event.group_id} 在黑名单中，已拦截 随机vv")
        return
    records = await _get_records()
    results = await asyncio.to_thread(
        random_pick, records, config.vv_min_similarity, 1)
    if not results:
        await random_vv.finish("字幕库里没有满足相似度条件的台词...")
    await send_vv_result(random_vv, results[0])


_SAY_RE = re.compile(r"[vVｖＶ]{1,2}\s*[说說]\s*(.+)", re.S)

vv_say = on_regex(rf"^{_PREFIX}[vVｖＶ]{{1,2}}\s*[说說]\s*(.+)$", priority=5, block=True)


@vv_say.handle()
async def handle_vv_say(event: MessageEvent):
    if isinstance(event, GroupMessageEvent) and await is_group_blocked(event.group_id):
        logger.info(f"[vv] 群 {event.group_id} 在黑名单中，已拦截 vv说")
        return
    m = _SAY_RE.search(event.get_message().extract_plain_text())
    query = m.group(1).strip() if m else ""
    if not query:
        await vv_say.finish("想找哪句台词？用法：vv说中国人你要自信")
    records = await _get_records()
    results = await asyncio.to_thread(
        search_local, records, query,
        config.vv_min_ratio, config.vv_min_similarity, 1)
    if not results:
        await vv_say.finish("没找到相关台词，换个说法试试吧")
    await send_vv_result(vv_say, results[0])


# ============================================================
# 管理命令：vv拉黑 / vv解拉黑 / vv黑名单（仅超级管理员）
# ============================================================
def _resolve_target_group(event: MessageEvent, args: Message) -> int | None:
    raw = args.extract_plain_text().strip()
    if raw.isdigit():
        return int(raw)
    if isinstance(event, GroupMessageEvent):
        return event.group_id
    return None


vv_blacklist_add = on_command("vv拉黑", permission=SUPERUSER, priority=1, block=True)


@vv_blacklist_add.handle()
async def handle_bl_add(event: MessageEvent, args: Message = CommandArg()):
    group_id = _resolve_target_group(event, args)
    if group_id is None:
        await vv_blacklist_add.finish("用法：vv拉黑 [群号]（在目标群内发送可省略群号）")
    async with async_session_factory() as session:
        stmt = select(VvGroupBlacklist.id).where(
            VvGroupBlacklist.group_id == group_id).limit(1)
        if (await session.execute(stmt)).first() is not None:
            await vv_blacklist_add.finish(f"群 {group_id} 已在黑名单中")
        session.add(VvGroupBlacklist(group_id=group_id, created_by=event.user_id))
        await session.commit()
    perm_cache.clear_pattern("vv:bl:")
    logger.info(f"[vv] 用户 {event.user_id} 将群 {group_id} 加入黑名单")
    await vv_blacklist_add.finish(f"已将群 {group_id} 加入 vv 黑名单")


vv_blacklist_remove = on_command("vv解拉黑", permission=SUPERUSER, priority=1, block=True)


@vv_blacklist_remove.handle()
async def handle_bl_remove(event: MessageEvent, args: Message = CommandArg()):
    group_id = _resolve_target_group(event, args)
    if group_id is None:
        await vv_blacklist_remove.finish("用法：vv解拉黑 [群号]（在目标群内发送可省略群号）")
    async with async_session_factory() as session:
        result = await session.execute(
            sa_delete(VvGroupBlacklist).where(VvGroupBlacklist.group_id == group_id))
        await session.commit()
    perm_cache.clear_pattern("vv:bl:")
    if result.rowcount == 0:
        await vv_blacklist_remove.finish(f"群 {group_id} 不在黑名单中")
    logger.info(f"[vv] 用户 {event.user_id} 将群 {group_id} 移出黑名单")
    await vv_blacklist_remove.finish(f"已将群 {group_id} 移出 vv 黑名单")


vv_blacklist_list = on_command("vv黑名单", permission=SUPERUSER, priority=1, block=True)


@vv_blacklist_list.handle()
async def handle_bl_list():
    async with async_session_factory() as session:
        rows = (await session.execute(
            select(VvGroupBlacklist).order_by(VvGroupBlacklist.created_at.desc())
        )).scalars().all()
    if not rows:
        await vv_blacklist_list.finish("vv 群黑名单为空")
    lines = [f"vv 群黑名单（共 {len(rows)} 个）："]
    lines += [f"{r.group_id}" + (f"（原因: {r.reason}）" if r.reason else "") for r in rows]
    await vv_blacklist_list.finish("\n".join(lines))

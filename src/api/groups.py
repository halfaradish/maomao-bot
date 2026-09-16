"""
群管理 API — 群列表/统计 + 群功能开关。

数据来源：
- group_statistics 表（群统计插件维护：群号/群名/功能标记）
- monitored_groups 表（群文件插件维护：爬取状态）
- bot.get_group_list()（实时：成员数/最大成员数，依赖 QQ 网关在线）
- messages_event_logs 聚合（消息量/活跃度）

群功能开关复用 auto_manage_group 插件的 FEATURE_MAP 与开关逻辑
（PermissionGroupPerm + GroupPermBinding + perm_cache 缓存清除），
与 QQ 命令「群管理 监控/取消监控」行为完全一致。
"""
import time
from typing import Optional

from fastapi import APIRouter, Depends, Query, Request
from nonebot import get_bot
from nonebot.adapters.onebot.v11 import Bot
from pydantic import BaseModel, Field
from sqlalchemy import func, select

from src.api.deps import TokenPayload, verify_token
from src.api.permissions import _build_page_data
from src.common.database import async_session_factory
from src.common.models.botdb_models import (
    GroupStatistic,
    MessageEventLog,
    MonitoredGroup,
)
from src.common.permission.cache import perm_cache
from src.common.permission.models import (
    GroupPermBinding,
    PermissionGroup,
    PermissionGroupPerm,
)
from src.config.response import error, success

router = APIRouter(prefix="/groups", tags=["群管理"])

# 告警日志功能的 perm_key（开关时需要额外清 ban_word_log_targets 缓存）
_BAN_WORD_LOG_TARGET_KEY = "auto_manage_group:ban_word_log_target"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _get_bot() -> Optional[Bot]:
    """获取当前 bot 实例，离线时返回 None"""
    try:
        return get_bot()
    except Exception:
        return None


def _get_feature_defs() -> list[dict]:
    """功能定义列表，与 auto_manage_group 的 FEATURE_MAP 保持一致。

    Returns:
        [{name, perm_key, pg_name}] — 前 4 项来自插件 FEATURE_MAP（单一数据源），
        最后一项为 group_sentinel 的入群审核。
    """
    from src.plugins.auto_manage_group import FEATURE_MAP  # 延迟导入，避免启动顺序问题

    defs = [
        {"name": name, "perm_key": perm_key, "pg_name": pg_name}
        for name, (perm_key, pg_name) in FEATURE_MAP.items()
    ]
    defs.append({
        "name": "入群审核",
        "perm_key": "group_sentinel:audit",
        "pg_name": "group_sentinel",
    })
    return defs


async def _fetch_group_stats_map() -> dict[int, dict]:
    """按群聚合消息日志：总量/活跃成员数/最近消息时间/近7天消息数"""
    seven_days_ago = int(time.time()) - 7 * 86400
    stmt = (
        select(
            MessageEventLog.group_id,
            func.count(MessageEventLog.id),
            func.count(func.distinct(MessageEventLog.user_id)),
            func.max(MessageEventLog.time),
            func.sum(func.if_(MessageEventLog.time >= seven_days_ago, 1, 0)),
        )
        .where(MessageEventLog.group_id.isnot(None))
        .group_by(MessageEventLog.group_id)
    )
    async with async_session_factory() as session:
        rows = (await session.execute(stmt)).all()
    return {
        int(row[0]): {
            "message_count": int(row[1] or 0),
            "active_member_count": int(row[2] or 0),
            "last_message_time": int(row[3]) if row[3] is not None else None,
            "last7d_message_count": int(row[4] or 0),
        }
        for row in rows
    }


# ---------------------------------------------------------------------------
# 群列表与统计
# ---------------------------------------------------------------------------


@router.get("/list", summary="列出所有群（含统计）")
async def list_groups(
    page: int = Query(1, ge=1, description="页码"),
    size: int = Query(20, ge=1, le=100, description="每页数量"),
    auth: TokenPayload = Depends(verify_token),
    request: Request = None,
):
    """合并多个数据源返回群列表：实时成员数 + 落库统计 + 消息活跃度。bot 离线时优雅降级。"""
    merged: dict[int, dict] = {}

    # 1. 实时群数据（成员数/最大成员数）
    bot = _get_bot()
    if bot:
        try:
            for g in await bot.get_group_list():
                merged.setdefault(int(g["group_id"]), {})["group_id"] = int(g["group_id"])
                entry = merged[int(g["group_id"])]
                entry["group_name"] = g.get("group_name", "")
                entry["member_count"] = g.get("member_count")
                entry["max_member_count"] = g.get("max_member_count")
        except Exception:
            pass  # 网关异常时降级为仅数据库数据

    # 2. group_statistics 表（落库的群号/群名/功能标记）
    async with async_session_factory() as session:
        stat_rows = (await session.execute(select(GroupStatistic))).scalars().all()
        mon_rows = (await session.execute(select(MonitoredGroup))).scalars().all()
    for g in stat_rows:
        try:
            gid = int(g.group_id)
        except (TypeError, ValueError):
            continue
        entry = merged.setdefault(gid, {"group_id": gid})
        entry.setdefault("group_name", g.group_name)
        entry["group_function"] = g.group_function or ""
    for m in mon_rows:
        entry = merged.setdefault(int(m.group_id), {"group_id": int(m.group_id)})
        entry.setdefault("group_name", m.group_name)
        entry["monitored"] = m.is_active
        entry["last_crawled_at"] = m.last_crawled_at.isoformat() if m.last_crawled_at else None

    # 3. 消息日志聚合
    stats_map = await _fetch_group_stats_map()
    for gid, stats in stats_map.items():
        entry = merged.setdefault(gid, {"group_id": gid})
        entry.update(stats)

    # 4. 归一化 + 排序（成员数降序，未知成员数的群排后面）
    items = []
    for gid, e in merged.items():
        items.append({
            "group_id": gid,
            "group_name": e.get("group_name", ""),
            "member_count": e.get("member_count"),
            "max_member_count": e.get("max_member_count"),
            "group_function": e.get("group_function", ""),
            "monitored": e.get("monitored"),
            "last_crawled_at": e.get("last_crawled_at"),
            "message_count": e.get("message_count", 0),
            "active_member_count": e.get("active_member_count", 0),
            "last7d_message_count": e.get("last7d_message_count", 0),
            "last_message_time": e.get("last_message_time"),
        })
    items.sort(
        key=lambda x: (
            x["member_count"] is None,
            -(x["member_count"] or 0),
            -x["group_id"],
        )
    )

    total = len(items)
    start = (page - 1) * size
    page_items = items[start:start + size]
    return success(data=_build_page_data(page_items, total, page, size), request=request)


@router.get("/{group_id}/stats", summary="单群统计")
async def get_group_stats(
    group_id: int,
    auth: TokenPayload = Depends(verify_token),
    request: Request = None,
):
    """返回单群的详细统计：成员数、消息总量、近7天消息、活跃成员、最近消息时间等。"""
    stats_map = await _fetch_group_stats_map()
    stats = stats_map.get(group_id, {
        "message_count": 0,
        "active_member_count": 0,
        "last_message_time": None,
        "last7d_message_count": 0,
    })

    member_count = None
    max_member_count = None
    group_name = ""
    bot = _get_bot()
    if bot:
        try:
            for g in await bot.get_group_list():
                if int(g["group_id"]) == group_id:
                    member_count = g.get("member_count")
                    max_member_count = g.get("max_member_count")
                    group_name = g.get("group_name", "")
                    break
        except Exception:
            pass

    async with async_session_factory() as session:
        stat = (await session.execute(
            select(GroupStatistic).where(GroupStatistic.group_id == str(group_id))
        )).scalars().first()
        monitored = (await session.execute(
            select(MonitoredGroup).where(MonitoredGroup.group_id == group_id)
        )).scalars().first()

    return success(
        data={
            "group_id": group_id,
            "group_name": group_name or (stat.group_name if stat else ""),
            "member_count": member_count,
            "max_member_count": max_member_count,
            "group_function": stat.group_function if stat else "",
            "monitored": monitored.is_active if monitored else None,
            "last_crawled_at": monitored.last_crawled_at.isoformat() if monitored and monitored.last_crawled_at else None,
            **stats,
        },
        request=request,
    )


# ---------------------------------------------------------------------------
# 群功能开关
# ---------------------------------------------------------------------------


@router.get("/features/{group_id}", summary="查看群功能开关状态")
async def get_group_features(
    group_id: int,
    auth: TokenPayload = Depends(verify_token),
    request: Request = None,
):
    """列出全部群级功能及当前开关状态（与运行时 is_group_feature_enabled 同源）。"""
    from src.plugins.auto_manage_group.group_checker import is_group_feature_enabled

    features = []
    for feat in _get_feature_defs():
        features.append({
            "name": feat["name"],
            "perm_key": feat["perm_key"],
            "enabled": await is_group_feature_enabled(group_id, feat["perm_key"]),
        })
    return success(data={"group_id": group_id, "features": features}, request=request)


class FeatureToggleRequest(BaseModel):
    """群功能开关请求"""
    perm_key: str = Field(..., description="权限点key，如 auto_manage_group:increase")
    enabled: bool = Field(..., description="true=开启 false=关闭")


@router.post("/features/{group_id}/toggle", summary="切换群功能开关")
async def toggle_group_feature(
    group_id: int,
    body: FeatureToggleRequest,
    auth: TokenPayload = Depends(verify_token),
    request: Request = None,
):
    """开启/关闭指定群的功能。逻辑与 QQ 命令「群管理 监控/取消监控」一致：
    维护 PermissionGroup + PermissionGroupPerm + GroupPermBinding 并清除相关缓存。
    """
    feat = next(
        (f for f in _get_feature_defs() if f["perm_key"] == body.perm_key),
        None,
    )
    if feat is None:
        return error(message=f"未知功能: {body.perm_key}", request=request)

    perm_key, pg_name, display_name = feat["perm_key"], feat["pg_name"], feat["name"]

    async with async_session_factory() as session:
        pg = (await session.execute(
            select(PermissionGroup).where(PermissionGroup.name == pg_name).limit(1)
        )).scalars().first()

        if body.enabled:
            # 开启：查找或创建权限组（含权限点），再绑定群
            if not pg:
                pg = PermissionGroup(
                    name=pg_name,
                    display_name=display_name,
                    description=f"自动创建：{display_name}功能权限组",
                    created_by=0,
                )
                session.add(pg)
                await session.flush()
                session.add(PermissionGroupPerm(group_id=pg.id, perm_key=perm_key))

            existing = (await session.execute(
                select(GroupPermBinding.id).where(
                    GroupPermBinding.qq_group_id == group_id,
                    GroupPermBinding.permission_group_id == pg.id,
                ).limit(1)
            )).first()
            if existing is None:
                session.add(GroupPermBinding(qq_group_id=group_id, permission_group_id=pg.id))
            await session.commit()
        else:
            # 关闭：删除群与该权限组的绑定
            bindings = []
            if pg:
                bindings = (await session.execute(
                    select(GroupPermBinding).where(
                        GroupPermBinding.qq_group_id == group_id,
                        GroupPermBinding.permission_group_id == pg.id,
                    )
                )).scalars().all()
                for binding in bindings:
                    await session.delete(binding)
                await session.commit()

    # 清除该群的群功能缓存；告警日志还需清目标群列表缓存
    perm_cache.delete(f"group_feature:{group_id}:{perm_key}")
    if perm_key == _BAN_WORD_LOG_TARGET_KEY:
        perm_cache.delete("ban_word_log_targets")

    return success(
        message=f"群 {group_id} 已{'开启' if body.enabled else '关闭'}功能: {display_name}",
        data={"group_id": group_id, "perm_key": perm_key, "enabled": body.enabled},
        request=request,
    )

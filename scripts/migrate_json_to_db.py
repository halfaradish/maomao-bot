#!/usr/bin/env python3
"""一次性迁移脚本：将 5 个插件的 JSON 存储数据导入 bot_db

迁移范围（仅活跃键，遗留白名单键已在权限系统，不再迁移）：
    duel.json           → duel_tags / duel_tag_aliases / duel_daily_problem_state
    fakemsg.json        → fakemsg_daily_usage（daily_times_log，usage_date 取 last_refresh_date）
    mass_kick.json      → mass_kick_managed_groups
    prd.json            → prd_todos（保留原编号；exist_groups 值打印供配置 PRD_EXIST_GROUPS）
    shit_transport.json → shit_transport_stats

运行方式：
    cd <项目根目录>
    python scripts/migrate_json_to_db.py [--archive]

特性：
- 幂等：select-before-insert / upsert，重复运行不产生重复数据
- 迁移前自动建表（Base.metadata.create_all，仅创建缺失表）
- --archive：全部段迁移成功后将源 JSON 重命名为 *.json.migrated（不删除，可回滚）
- 输出各段 {migrated, skipped_existing, errors} 迁移报告
"""
import argparse
import asyncio
import json
import os
import sys
from datetime import date, datetime
from pathlib import Path

# 确保项目根目录在 sys.path 中
PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

# 加载环境变量：先加载 .env 获取 ENVIRONMENT，再加载 .env.{ENVIRONMENT}
from dotenv import load_dotenv

load_dotenv(str(PROJECT_ROOT / ".env"), override=True)
_env = os.environ.get("ENVIRONMENT", "dev")
_env_file = PROJECT_ROOT / f".env.{_env}"
if _env_file.exists():
    load_dotenv(str(_env_file), override=True)

# 初始化 NoneBot（src.common.__init__ 会调用 get_driver()）
import nonebot

nonebot.init()

from sqlalchemy import select
from sqlalchemy.dialects.mysql import insert as mysql_insert

from src.common.database import Base, engine, get_session, current_env_tag
from src.common.models.duel_models import DuelDailyProblemState, DuelStandardTag, DuelTagAlias
from src.common.models.fakemsg_models import FakemsgDailyUsage
from src.common.models.mass_kick_models import MassKickManagedGroup
from src.common.models.prd_models import PrdTodo
from src.common.models.shit_transport_models import ShitTransportStats

# 与 JsonUtils 一致：优先 NONEBOT_DATA_DIR，兼容旧脚本变量，默认仓库 data/
DATA_DIR = Path(
    os.environ.get("NONEBOT_DATA_DIR")
    or os.environ.get("DI_TING_DATA_DIR")
    or PROJECT_ROOT / "data"
)


def _read_json(filename: str) -> dict | None:
    """直读 JSON 文件（不经过 JsonUtils，避免建文件/合并副作用）"""
    path = DATA_DIR / filename
    if not path.exists():
        return None
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def _parse_date(value) -> date | None:
    """解析 'YYYY-MM-DD' 字符串，空/非法返回 None"""
    if not value:
        return None
    try:
        return datetime.strptime(str(value), "%Y-%m-%d").date()
    except ValueError:
        return None


# ============================================================
# duel
# ============================================================
async def migrate_duel(stats: dict) -> None:
    data = _read_json("duel.json")
    if data is None:
        stats["notes"].append("duel.json 不存在，跳过")
        return

    env_tag = current_env_tag()
    tag_map: dict = data.get("map") or {}
    daily: dict = data.get("daily_problems") or {}

    async with get_session() as session:
        # 标准标签词表（含空别名列表的键）
        for tag in tag_map:
            exists = await session.scalar(
                select(DuelStandardTag.id).where(
                    DuelStandardTag.env_tag == env_tag,
                    DuelStandardTag.tag == tag,
                )
            )
            if exists is not None:
                stats["skipped_existing"] += 1
                continue
            session.add(DuelStandardTag(env_tag=env_tag, tag=tag))
            stats["migrated"] += 1

        # 别名映射（quick_map 为反向索引，不迁移）
        for tag, aliases in tag_map.items():
            for alias in (aliases or []):
                exists = await session.scalar(
                    select(DuelTagAlias.id).where(
                        DuelTagAlias.env_tag == env_tag,
                        DuelTagAlias.alias == alias,
                    )
                )
                if exists is not None:
                    stats["skipped_existing"] += 1
                    continue
                session.add(DuelTagAlias(env_tag=env_tag, tag=tag, alias=alias))
                stats["migrated"] += 1

        await session.flush()

        # 每日一题状态（每环境单行 upsert）
        if daily:
            state_values = {
                "env_tag": env_tag,
                "current_date": _parse_date(daily.get("current_date")),
                "current_problem": daily.get("current_problem"),
                "history": daily.get("history") or [],
            }
            existing_state = await session.scalar(
                select(DuelDailyProblemState.id).where(
                    DuelDailyProblemState.env_tag == env_tag
                )
            )
            if existing_state is not None:
                stmt = mysql_insert(DuelDailyProblemState).values(**state_values)
                stmt = stmt.on_duplicate_key_update(
                    current_date=stmt.inserted.current_date,
                    current_problem=stmt.inserted.current_problem,
                    history=stmt.inserted.history,
                )
                await session.execute(stmt)
                stats["skipped_existing"] += 1
            else:
                session.add(DuelDailyProblemState(**state_values))
                stats["migrated"] += 1


# ============================================================
# fakemsg
# ============================================================
async def migrate_fakemsg(stats: dict) -> None:
    data = _read_json("fakemsg.json")
    if data is None:
        stats["notes"].append("fakemsg.json 不存在，跳过")
        return

    env_tag = current_env_tag()
    daily_times_log: dict = data.get("daily_times_log") or {}
    usage_date = _parse_date(data.get("last_refresh_date")) or date.today()

    async with get_session() as session:
        for user_id, count in daily_times_log.items():
            exists = await session.scalar(
                select(FakemsgDailyUsage.id).where(
                    FakemsgDailyUsage.env_tag == env_tag,
                    FakemsgDailyUsage.user_id == int(user_id),
                    FakemsgDailyUsage.usage_date == usage_date,
                )
            )
            if exists is not None:
                stats["skipped_existing"] += 1
                continue
            session.add(FakemsgDailyUsage(
                env_tag=env_tag, user_id=int(user_id),
                usage_date=usage_date, count=int(count),
            ))
            stats["migrated"] += 1


# ============================================================
# mass_kick
# ============================================================
async def migrate_mass_kick(stats: dict) -> None:
    data = _read_json("mass_kick.json")
    if data is None:
        stats["notes"].append("mass_kick.json 不存在，跳过")
        return

    env_tag = current_env_tag()
    managed_groups: list = data.get("managed_groups") or []

    async with get_session() as session:
        for group_id in managed_groups:
            gid = int(group_id)
            exists = await session.scalar(
                select(MassKickManagedGroup.id).where(
                    MassKickManagedGroup.env_tag == env_tag,
                    MassKickManagedGroup.group_id == gid,
                )
            )
            if exists is not None:
                stats["skipped_existing"] += 1
                continue
            session.add(MassKickManagedGroup(env_tag=env_tag, group_id=gid))
            stats["migrated"] += 1


# ============================================================
# prd
# ============================================================
async def migrate_prd(stats: dict) -> None:
    data = _read_json("prd.json")
    if data is None:
        stats["notes"].append("prd.json 不存在，跳过")
        return

    env_tag = current_env_tag()
    exist_groups: list = data.get("exist_groups") or []
    to_do: list = data.get("to_do") or []

    # exist_groups 已改为插件配置，检测到手改数据时提示写入 .env
    if exist_groups:
        stats["notes"].append(
            f"检测到 exist_groups={exist_groups}，已改为插件配置，"
            f"请在 .env.{_env} 设置 PRD_EXIST_GROUPS='[{','.join(repr(g) for g in exist_groups)}]'"
        )

    async with get_session() as session:
        for item in to_do:
            todo_id = int(item["id"])
            exists = await session.get(PrdTodo, todo_id)
            if exists is not None and exists.env_tag == env_tag:
                stats["skipped_existing"] += 1
                continue
            if exists is not None:
                # 同编号已被其他环境占用：自增主键全局唯一，追加到尾部
                stats["notes"].append(
                    f"prd 编号 {todo_id} 已被其他环境占用，该条以新编号追加"
                )
            session.add(PrdTodo(
                id=todo_id,
                env_tag=env_tag,
                content=item.get("content", ""),
                finish=bool(item.get("finish", False)),
                group_name=item.get("group", "其他") or "其他",
                priority=item.get("priority", "medium") or "medium",
                create_by=item.get("create_by", "") or "",
                create_at=_parse_date(item.get("create_at")),
                last_modify_by=item.get("last_modify_by", "") or "",
                last_modify_at=_parse_date(item.get("last_modify_at")),
                finish_by=item.get("finish_by", "") or "",
                finish_at=_parse_date(item.get("finish_at")),
                assign_to=item.get("assign_to") or None,
                assign_at=_parse_date(item.get("assign_at")),
                assign_by=item.get("assign_by") or None,
            ))
            stats["migrated"] += 1


# ============================================================
# shit_transport
# ============================================================
async def migrate_shit_transport(stats: dict) -> None:
    data = _read_json("shit_transport.json")
    if data is None:
        stats["notes"].append("shit_transport.json 不存在，跳过")
        return

    env_tag = current_env_tag()
    kind_map = {
        "banshi_frequency_statistics": "banshi",
        "postshi_frequency_statistics": "postshi",
    }

    async with get_session() as session:
        for json_key, kind in kind_map.items():
            for user_id, info in (data.get(json_key) or {}).items():
                exists = await session.scalar(
                    select(ShitTransportStats.id).where(
                        ShitTransportStats.env_tag == env_tag,
                        ShitTransportStats.user_id == int(user_id),
                        ShitTransportStats.kind == kind,
                    )
                )
                if exists is not None:
                    stats["skipped_existing"] += 1
                    continue
                session.add(ShitTransportStats(
                    env_tag=env_tag,
                    user_id=int(user_id),
                    kind=kind,
                    count=int(info.get("count", 0)),
                    nickname=info.get("nickname", "") or "",
                ))
                stats["migrated"] += 1


# ============================================================
# 主流程
# ============================================================
SECTIONS = {
    "duel": migrate_duel,
    "fakemsg": migrate_fakemsg,
    "mass_kick": migrate_mass_kick,
    "prd": migrate_prd,
    "shit_transport": migrate_shit_transport,
}


async def main(archive: bool) -> int:
    # 建表（幂等，仅创建缺失表）
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    report: dict[str, dict] = {}
    ok = True
    for name, fn in SECTIONS.items():
        stats = {"migrated": 0, "skipped_existing": 0, "notes": [], "errors": []}
        try:
            await fn(stats)
        except Exception as e:
            stats["errors"].append(f"迁移异常: {e}")
        report[name] = stats
        if stats["errors"]:
            ok = False

    print("\n========== JSON → bot_db 迁移报告 ==========")
    for name, stats in report.items():
        print(f"[{name}] migrated={stats['migrated']} "
              f"skipped_existing={stats['skipped_existing']} "
              f"notes={len(stats['notes'])} errors={len(stats['errors'])}")
        for note in stats["notes"]:
            print(f"    * {note}")
        for err in stats["errors"]:
            print(f"    ! {err}")

    if archive and ok:
        print("\n归档源文件：")
        for filename in ("duel.json", "fakemsg.json", "mass_kick.json",
                         "prd.json", "shit_transport.json"):
            path = DATA_DIR / filename
            if path.exists():
                target = path.with_suffix(".json.migrated")
                path.rename(target)
                print(f"    {path} -> {target}")
    elif archive:
        print("\n存在错误，未执行归档。修正后重新运行（脚本幂等）。")

    return 0 if ok else 1


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="插件 JSON 数据迁移至 bot_db")
    parser.add_argument("--archive", action="store_true",
                        help="迁移成功后将源 JSON 重命名为 *.json.migrated")
    args = parser.parse_args()
    sys.exit(asyncio.run(main(args.archive)))

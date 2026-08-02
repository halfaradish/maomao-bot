#!/usr/bin/env python3
"""一次性迁移脚本：将各插件的 JSON 白名单/目标群列表导入权限系统

运行方式：
    cd <项目根目录>
    python scripts/migrate_json_whitelist.py

特性：
- 自动清理旧迁移数据后重新迁移
- 幂等：重复运行不会产生重复数据
- 保留 JSON 原文件不动，只读取并写入权限系统 DB
- 每个权限组只含一个权限点，避免群绑定交叉污染
- 输出详细迁移报告
"""
import asyncio
import json
import os
import sys
from pathlib import Path
from typing import Optional

# 确保项目根目录在 sys.path 中
PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

# 加载环境变量：先加载 .env 获取 ENVIRONMENT，再加载 .env.{ENVIRONMENT}
from dotenv import load_dotenv
load_dotenv(str(PROJECT_ROOT / ".env"), override=True)
_env = os.environ.get("ENVIRONMENT", "prod")
_env_file = PROJECT_ROOT / f".env.{_env}"
if _env_file.exists():
    load_dotenv(str(_env_file), override=True)

# 初始化 NoneBot（src.common.__init__ 会调用 get_driver()）
import nonebot
nonebot.init()

from sqlalchemy import select, delete
from src.common.database import async_session_factory
from src.common.permission.models import (
    PermissionPoint,
    PermissionGroup,
    PermissionGroupMember,
    PermissionGroupPerm,
    GroupPermBinding,
)
from src.common.permission.cache import perm_cache

DATA_DIR = Path(os.environ.get("DI_TING_DATA_DIR", "data"))

# ============================================================
# 旧数据清理：删除上次迁移产生的权限组及其关联数据
# ============================================================
# 这些权限组名是旧版迁移脚本创建的，需要清理后重建
OLD_PG_NAMES = [
    "group_ban_users",
    "group_msg_del_users",
    "group_statistics_managers",
    "prd_users",
    "sub_records_users",       # 旧版混了 use + notify
    "check_up_users",          # 旧版混了 use + notify
    "mass_kick_users",
    "group_send_users",
    "group_card_changer_targets",
    "shadow_problem_view_targets",
    "real_time_problems_targets",
    "contest_reminder_targets",
    "shit_transport_config",   # 旧版混了 use + receive
    # 新版拆分后的名称也加入清理列表，确保重跑时完全重建
    "sub_records_notify",
    "check_up_notify",
    "shit_transport_post",
    "shit_transport_receive",
]

# ============================================================
# 迁移配置
# ============================================================
# 每个条目定义一个权限组（只含一个权限点）、用户白名单、群绑定
# 多权限点的插件拆成多个条目，确保群绑定不会交叉污染

MIGRATIONS = [
    # --- 类型 A: JSON 白名单鉴权 ---

    # 1. group_ban
    {
        "plugin": "group_ban",
        "pg_name": "group_ban_users",
        "pg_display": "群禁言白名单",
        "pg_desc": "自动迁移：群禁言/踢人功能使用权限",
        "perms": [
            ("group_ban:use", "群禁言使用", "允许使用 ban/unban/kick 命令"),
        ],
        "json_file": "ban_whitelist.json",
        "user_fields": ["user_whitelist"],
        "group_fields": [("group_whitelist", "group_ban:use")],
    },

    # 2. group_msg_del
    {
        "plugin": "group_msg_del",
        "pg_name": "group_msg_del_users",
        "pg_display": "群消息撤回白名单",
        "pg_desc": "自动迁移：群消息撤回功能使用权限",
        "perms": [
            ("group_msg_del:use", "群消息撤回使用", "允许使用撤回命令"),
        ],
        "json_file": "group_msg_del.json",
        "user_fields": ["user_whitelist"],
        "group_fields": [],
    },

    # 3. group_statistics
    {
        "plugin": "group_statistics",
        "pg_name": "group_statistics_managers",
        "pg_display": "群统计管理白名单",
        "pg_desc": "自动迁移：群统计 add/update/rm 管理权限",
        "perms": [
            ("group_statistics:manage", "群统计管理", "允许添加/修改/删除群聊信息"),
        ],
        "json_file": "group_statistics.json",
        "user_fields": ["userid"],
        "group_fields": [],
    },

    # 4. prd
    {
        "plugin": "prd",
        "pg_name": "prd_users",
        "pg_display": "需求管理白名单",
        "pg_desc": "自动迁移：需求管理功能使用权限",
        "perms": [
            ("prd:use", "需求管理使用", "允许使用 prd 命令"),
        ],
        "json_file": "prd.json",
        "user_fields": ["whitelist_person"],
        "group_fields": [("whitelist_groups", "prd:use")],
    },

    # 5a. sub_records - 鉴权
    {
        "plugin": "sub_records",
        "pg_name": "sub_records_users",
        "pg_display": "过题统计白名单",
        "pg_desc": "自动迁移：过题统计功能使用权限",
        "perms": [
            ("sub_records:use", "过题统计使用", "允许使用 过题 命令"),
        ],
        "json_file": "sub_records.json",
        "user_fields": ["person_users"],
        "group_fields": [("group_users", "sub_records:use")],
    },

    # 5b. sub_records - 推送
    {
        "plugin": "sub_records",
        "pg_name": "sub_records_notify",
        "pg_display": "过题统计推送目标群",
        "pg_desc": "自动迁移：过题统计定时推送的目标群",
        "perms": [
            ("sub_records:notify", "过题统计推送", "定时推送过题排名的目标群"),
        ],
        "json_file": "sub_records.json",
        "user_fields": [],
        "group_fields": [("submission_groups", "sub_records:notify")],
    },

    # 6a. check_up - 鉴权
    {
        "plugin": "check_up",
        "pg_name": "check_up_users",
        "pg_display": "考勤管理白名单",
        "pg_desc": "自动迁移：考勤管理功能使用权限",
        "perms": [
            ("check_up:use", "考勤使用", "允许使用 考勤 命令"),
        ],
        "json_file": "check_up.json",
        "user_fields": ["person_whitelist"],
        "group_fields": [("group_whitelist", "check_up:use")],
    },

    # 6b. check_up - 推送
    {
        "plugin": "check_up",
        "pg_name": "check_up_notify",
        "pg_display": "考勤推送目标群",
        "pg_desc": "自动迁移：考勤定时推送的目标群",
        "perms": [
            ("check_up:notify", "考勤推送", "定时推送考勤信息的目标群"),
        ],
        "json_file": "check_up.json",
        "user_fields": [],
        "group_fields": [("group_id", "check_up:notify")],
    },

    # --- 类型 B: 超级管理员硬编码 -> 权限系统（无数据迁移，仅注册权限点） ---

    # 7. mass_kick
    {
        "plugin": "mass_kick",
        "pg_name": "mass_kick_users",
        "pg_display": "一键退群权限",
        "pg_desc": "自动创建：一键退群功能使用权限",
        "perms": [
            ("mass_kick:use", "一键退群使用", "允许使用 一键退群 命令"),
        ],
        "json_file": None,
        "user_fields": [],
        "group_fields": [],
    },

    # 8. group_send
    {
        "plugin": "group_send",
        "pg_name": "group_send_users",
        "pg_display": "分组发送权限",
        "pg_desc": "自动创建：分组发送功能使用权限",
        "perms": [
            ("group_send:use", "分组发送使用", "允许使用 分组发送 命令"),
        ],
        "json_file": None,
        "user_fields": [],
        "group_fields": [],
    },

    # --- 类型 C: JSON 群列表作为推送/路由目标 ---

    # 9. group_card_changer
    {
        "plugin": "group_card_changer",
        "pg_name": "group_card_changer_targets",
        "pg_display": "群昵称更新目标群",
        "pg_desc": "自动迁移：定时更新机器人昵称的目标群",
        "perms": [
            ("group_card_changer:auto_update", "群昵称自动更新", "定时更新机器人昵称的目标群"),
        ],
        "json_file": "nickname_changer.json",
        "user_fields": [],
        "group_fields": [("group_whitelist", "group_card_changer:auto_update")],
    },

    # 10. shadow_problem_view
    {
        "plugin": "shadow_problem_view",
        "pg_name": "shadow_problem_view_targets",
        "pg_display": "影子过题推送目标群",
        "pg_desc": "自动迁移：影子过题定时推送的目标群",
        "perms": [
            ("shadow_problem_view:notify", "影子过题推送", "影子过题定时推送的目标群"),
        ],
        "json_file": "shadow_problem_view.json",
        "user_fields": [],
        "group_fields": [("groups_send_by_plugin", "shadow_problem_view:notify")],
    },

    # 11. real_time_problems
    {
        "plugin": "real_time_problems",
        "pg_name": "real_time_problems_targets",
        "pg_display": "实时过题推送目标群",
        "pg_desc": "自动迁移：实时过题定时推送的目标群",
        "perms": [
            ("real_time_problems:notify", "实时过题推送", "实时过题定时推送的目标群"),
        ],
        "json_file": "real_time_problems.json",
        "user_fields": [],
        "group_fields": [("target_groups", "real_time_problems:notify")],
    },

    # 12. contest_reminder
    {
        "plugin": "contest_reminder",
        "pg_name": "contest_reminder_targets",
        "pg_display": "比赛提醒推送目标群",
        "pg_desc": "自动迁移：比赛提醒定时推送的目标群",
        "perms": [
            ("contest_reminder:notify", "比赛提醒推送", "比赛提醒定时推送的目标群"),
        ],
        "json_file": "contest_reminder.json",
        "user_fields": [],
        "group_fields": [("groups_send_by_plugin", "contest_reminder:notify")],
    },

    # 13a. shit_transport - 可发送群
    {
        "plugin": "shit_transport",
        "pg_name": "shit_transport_post",
        "pg_display": "搬史可发送群",
        "pg_desc": "自动迁移：允许使用搬史命令的群",
        "perms": [
            ("shit_transport:use", "搬史使用", "允许在群内使用搬史命令（可发送群）"),
        ],
        "json_file": "shit_transport.json",
        "user_fields": [],
        "group_fields": [("post_groups", "shit_transport:use")],
    },

    # 13b. shit_transport - 接收群
    {
        "plugin": "shit_transport",
        "pg_name": "shit_transport_receive",
        "pg_display": "搬史接收群",
        "pg_desc": "自动迁移：接收搬史转发消息的群",
        "perms": [
            ("shit_transport:receive", "搬史接收", "接收搬史转发消息的群"),
        ],
        "json_file": "shit_transport.json",
        "user_fields": [],
        "group_fields": [("receive_groups", "shit_transport:receive")],
    },
]


# ============================================================
# 迁移逻辑
# ============================================================

class MigrationReport:
    def __init__(self):
        self.lines: list[str] = []
        self.total_users_added = 0
        self.total_users_skipped = 0
        self.total_groups_added = 0
        self.total_groups_skipped = 0
        self.total_perms_registered = 0
        self.total_pg_created = 0
        self.total_pg_cleaned = 0
        self.total_bindings_cleaned = 0
        self.total_members_cleaned = 0

    def add(self, line: str):
        self.lines.append(line)

    def __str__(self):
        header = (
            f"\n{'=' * 60}\n"
            f"  权限系统迁移报告\n"
            f"{'=' * 60}\n"
        )
        footer = (
            f"\n{'=' * 60}\n"
            f"  清理：删除权限组 {self.total_pg_cleaned} 个，"
            f"群绑定 {self.total_bindings_cleaned} 条，"
            f"成员 {self.total_members_cleaned} 条\n"
            f"  新增：权限组 {self.total_pg_created} 个，"
            f"权限点 {self.total_perms_registered} 个\n"
            f"  用户导入：新增 {self.total_users_added}，跳过 {self.total_users_skipped}\n"
            f"  群绑定导入：新增 {self.total_groups_added}，跳过 {self.total_groups_skipped}\n"
            f"{'=' * 60}\n"
        )
        return header + "\n".join(self.lines) + footer


def _read_json(filename: str) -> Optional[dict]:
    """读取 data 目录下的 JSON 文件"""
    path = DATA_DIR / filename
    if not path.exists():
        return None
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception as e:
        print(f"  ⚠ 读取 {path} 失败: {e}")
        return None


def _extract_group_ids(data: dict, field: str) -> list[int]:
    """从 JSON 字段中提取群号列表，兼容字符串/整数/字典格式"""
    raw_list = data.get(field, [])
    if not isinstance(raw_list, list):
        return []
    result = []
    for item in raw_list:
        if isinstance(item, dict):
            gid = item.get("group_id")
            if gid is not None:
                result.append(int(gid))
        elif isinstance(item, (str, int)):
            result.append(int(item))
    return result


def _extract_user_ids(data: dict, fields: list[str]) -> list[int]:
    """从多个 JSON 字段中提取用户 QQ 号"""
    result = []
    for field in fields:
        raw_list = data.get(field, [])
        if not isinstance(raw_list, list):
            continue
        for item in raw_list:
            if isinstance(item, (str, int)):
                try:
                    result.append(int(item))
                except ValueError:
                    pass
    return result


async def cleanup_old_data(report: MigrationReport):
    """清理旧迁移产生的权限组及其关联数据"""
    report.add(f"\n{'─' * 40}")
    report.add("  清理旧数据")
    report.add(f"{'─' * 40}")

    async with async_session_factory() as session:
        # 查找所有需要清理的权限组
        result = await session.execute(
            select(PermissionGroup).where(PermissionGroup.name.in_(OLD_PG_NAMES))
        )
        old_groups = result.scalars().all()

        if not old_groups:
            report.add("  ℹ  无旧数据需要清理")
            return

        old_group_ids = [g.id for g in old_groups]
        old_group_names = [g.name for g in old_groups]

        # 1. 删除群绑定
        result = await session.execute(
            select(GroupPermBinding).where(
                GroupPermBinding.permission_group_id.in_(old_group_ids)
            )
        )
        bindings = result.scalars().all()
        for b in bindings:
            await session.delete(b)
        report.total_bindings_cleaned += len(bindings)

        # 2. 删除成员（PermissionGroupMember 有 cascade，但显式删除更安全）
        result = await session.execute(
            select(PermissionGroupMember).where(
                PermissionGroupMember.group_id.in_(old_group_ids)
            )
        )
        members = result.scalars().all()
        for m in members:
            await session.delete(m)
        report.total_members_cleaned += len(members)

        # 3. 删除权限点绑定（PermissionGroupPerm 有 cascade，但显式删除更安全）
        await session.execute(
            delete(PermissionGroupPerm).where(
                PermissionGroupPerm.group_id.in_(old_group_ids)
            )
        )

        # 4. 删除权限组
        for g in old_groups:
            await session.delete(g)
        report.total_pg_cleaned += len(old_groups)

        await session.commit()

        report.add(f"  🗑  删除权限组: {', '.join(old_group_names)}")
        report.add(f"  🗑  清理群绑定: {len(bindings)} 条")
        report.add(f"  🗑  清理成员: {len(members)} 条")


async def ensure_permission_point(session, perm_key: str, name: str, description: str, plugin_name: str) -> bool:
    """确保权限点已注册，返回 True 表示新增"""
    existing = (await session.execute(
        select(PermissionPoint).where(PermissionPoint.perm_key == perm_key).limit(1)
    )).scalars().first()
    if existing:
        return False
    session.add(PermissionPoint(
        plugin_name=plugin_name,
        perm_key=perm_key,
        name=name,
        description=description,
    ))
    await session.flush()
    return True


async def ensure_permission_group(session, pg_name: str, display_name: str, description: str) -> tuple[PermissionGroup, bool]:
    """确保权限组存在，返回 (group, is_new)"""
    existing = (await session.execute(
        select(PermissionGroup).where(PermissionGroup.name == pg_name).limit(1)
    )).scalars().first()
    if existing:
        return existing, False
    pg = PermissionGroup(
        name=pg_name,
        display_name=display_name,
        description=description,
        created_by=0,
    )
    session.add(pg)
    await session.flush()
    return pg, True


async def ensure_group_perm(session, group_id: int, perm_key: str) -> bool:
    """确保权限组绑定了指定权限点，返回 True 表示新增"""
    existing = (await session.execute(
        select(PermissionGroupPerm.id).where(
            PermissionGroupPerm.group_id == group_id,
            PermissionGroupPerm.perm_key == perm_key,
        ).limit(1)
    )).first()
    if existing:
        return False
    session.add(PermissionGroupPerm(group_id=group_id, perm_key=perm_key))
    return True


async def ensure_member(session, group_id: int, user_id: int) -> bool:
    """确保用户是权限组成员，返回 True 表示新增"""
    existing = (await session.execute(
        select(PermissionGroupMember.id).where(
            PermissionGroupMember.group_id == group_id,
            PermissionGroupMember.user_id == user_id,
        ).limit(1)
    )).first()
    if existing:
        return False
    session.add(PermissionGroupMember(group_id=group_id, user_id=user_id))
    return True


async def ensure_binding(session, qq_group_id: int, permission_group_id: int) -> bool:
    """确保群绑定了权限组，返回 True 表示新增"""
    existing = (await session.execute(
        select(GroupPermBinding.id).where(
            GroupPermBinding.qq_group_id == qq_group_id,
            GroupPermBinding.permission_group_id == permission_group_id,
        ).limit(1)
    )).first()
    if existing:
        return False
    session.add(GroupPermBinding(qq_group_id=qq_group_id, permission_group_id=permission_group_id))
    return True


async def migrate_one(config: dict, report: MigrationReport):
    """执行单个权限组的迁移"""
    plugin = config["plugin"]
    report.add(f"\n--- {plugin} / {config['pg_name']} ---")

    async with async_session_factory() as session:
        # 1. 注册权限点
        for perm_key, perm_name, perm_desc in config["perms"]:
            is_new = await ensure_permission_point(
                session, perm_key, perm_name, perm_desc, plugin
            )
            if is_new:
                report.total_perms_registered += 1
                report.add(f"  ✅ 注册权限点: {perm_key}")
            else:
                report.add(f"  ✓  权限点已存在: {perm_key}")

        # 2. 创建权限组
        pg, pg_is_new = await ensure_permission_group(
            session, config["pg_name"], config["pg_display"], config["pg_desc"]
        )
        if pg_is_new:
            report.total_pg_created += 1
            report.add(f"  ✅ 创建权限组: {config['pg_name']} (id={pg.id})")
        else:
            report.add(f"  ✓  权限组已存在: {config['pg_name']} (id={pg.id})")

        # 3. 确保权限组绑定了权限点
        for perm_key, _, _ in config["perms"]:
            added = await ensure_group_perm(session, pg.id, perm_key)
            if added:
                report.add(f"  ✅ 权限组绑定权限点: {perm_key}")

        await session.commit()

    # 4. 读取 JSON 数据并迁移
    if not config["json_file"]:
        report.add(f"  ℹ  无 JSON 数据文件（仅注册权限点）")
        return

    json_data = _read_json(config["json_file"])
    if json_data is None:
        report.add(f"  ℹ  JSON 文件不存在: {config['json_file']}")
        return

    async with async_session_factory() as session:
        pg = (await session.execute(
            select(PermissionGroup).where(PermissionGroup.name == config["pg_name"]).limit(1)
        )).scalars().first()

        # 5. 迁移用户白名单
        user_ids = _extract_user_ids(json_data, config["user_fields"])
        if user_ids:
            report.add(f"  ℹ  用户白名单: {len(user_ids)} 个 -> {user_ids}")
            for uid in user_ids:
                added = await ensure_member(session, pg.id, uid)
                if added:
                    report.total_users_added += 1
                else:
                    report.total_users_skipped += 1
        else:
            if config["user_fields"]:
                report.add(f"  ℹ  用户白名单为空")

        # 6. 迁移群绑定
        for json_field, perm_key in config["group_fields"]:
            group_ids = _extract_group_ids(json_data, json_field)
            if not group_ids:
                report.add(f"  ℹ  群列表为空: {json_field} -> {perm_key}")
                continue

            await ensure_group_perm(session, pg.id, perm_key)

            added_cnt = 0
            skipped_cnt = 0
            for gid in group_ids:
                added = await ensure_binding(session, gid, pg.id)
                if added:
                    added_cnt += 1
                    report.total_groups_added += 1
                else:
                    skipped_cnt += 1
                    report.total_groups_skipped += 1
            report.add(
                f"  ✅ 群绑定: {json_field} -> {perm_key}: "
                f"新增 {added_cnt}，跳过 {skipped_cnt}"
            )

        await session.commit()


async def main():
    print("权限系统迁移脚本")
    print(f"数据目录: {DATA_DIR.resolve()}")
    print(f"数据库: {os.environ.get('BOT_DB_HOST', '?')}:{os.environ.get('BOT_DB_PORT', '?')}/{os.environ.get('BOT_DB_NAME', '?')}")
    print()

    report = MigrationReport()

    # Step 1: 清理旧数据
    await cleanup_old_data(report)

    # Step 2: 重新迁移
    for config in MIGRATIONS:
        await migrate_one(config, report)

    # Step 3: 清除权限缓存
    perm_cache.clear_all()
    report.add("\n🧹 已清除权限缓存")

    print(str(report))


if __name__ == "__main__":
    asyncio.run(main())

"""一次性迁移脚本：将 auto_manage_group.json 数据迁移到权限系统 GroupPermBinding

使用方式：
  1. 在 bot 启动时自动调用（通过 _ensure_default_perm_groups + 迁移逻辑）
  2. 或手动运行: python -m src.plugins.auto_manage_group.migrate

迁移映射：
  monitored_groups           → GroupPermBinding → auto_manage_increase + auto_manage_decrease
  ban_words_monitored_groups → GroupPermBinding → auto_manage_ban_word
  ban_words_remind_groups    → GroupPermBinding → auto_manage_ban_word_log

迁移完成后，JSON 文件可删除或保留作为备份。
"""
import asyncio
import logging
import os

from sqlalchemy import select

from src.common import JsonUtils
from src.common.database import async_session_factory
from src.common.permission.models import (
    PermissionGroup,
    PermissionGroupPerm,
    GroupPermBinding,
)
from src.common.permission.cache import perm_cache

logger = logging.getLogger(__name__)

# 默认权限组定义
DEFAULT_GROUPS = {
    "auto_manage_increase": {
        "display_name": "入群欢迎",
        "perm_key": "auto_manage_group:increase",
    },
    "auto_manage_decrease": {
        "display_name": "离群通知",
        "perm_key": "auto_manage_group:decrease",
    },
    "auto_manage_ban_word": {
        "display_name": "违禁词检测",
        "perm_key": "auto_manage_group:ban_word_detect",
    },
    "auto_manage_ban_word_log": {
        "display_name": "违禁词告警日志",
        "perm_key": "auto_manage_group:ban_word_log_target",
    },
}

# JSON 列表 → 权限组名的映射
LIST_TO_PG_MAP = {
    "monitored_groups": ["auto_manage_increase", "auto_manage_decrease"],
    "ban_words_monitored_groups": ["auto_manage_ban_word"],
    "ban_words_remind_groups": ["auto_manage_ban_word_log"],
}


async def _ensure_permission_groups(session) -> dict[str, PermissionGroup]:
    """确保所有默认权限组存在，返回 {group_name: PermissionGroup} 映射"""
    pg_map: dict[str, PermissionGroup] = {}
    for pg_name, info in DEFAULT_GROUPS.items():
        result = await session.execute(
            select(PermissionGroup).where(PermissionGroup.name == pg_name).limit(1)
        )
        pg = result.scalars().first()
        if not pg:
            pg = PermissionGroup(
                name=pg_name,
                display_name=info["display_name"],
                description=f"迁移自动创建：{info['display_name']}功能权限组",
                created_by=0,
            )
            session.add(pg)
            await session.flush()
            session.add(PermissionGroupPerm(group_id=pg.id, perm_key=info["perm_key"]))
            logger.info(f"[migrate] 创建权限组: {pg_name}")

        pg_map[pg_name] = pg
    await session.commit()
    return pg_map


async def migrate_from_json(data_filename: str = "auto_manage_group.json") -> dict:
    """从 JSON 文件迁移数据到 GroupPermBinding

    Args:
        data_filename: JSON 文件名（相对于数据目录）

    Returns:
        dict: 迁移统计 {"migrated_groups": int, "skipped_existing": int, "errors": list[str]}
    """
    stats = {"migrated_groups": 0, "skipped_existing": 0, "errors": []}

    # 读取 JSON 文件
    data, _ = JsonUtils.read(filename=data_filename, default={})
    if not data:
        logger.info("[migrate] JSON 文件为空或不存在，跳过迁移")
        stats["errors"].append("JSON 文件为空或不存在")
        return stats

    async with async_session_factory() as session:
        # 确保权限组存在
        pg_map = await _ensure_permission_groups(session)

        for json_key, pg_names in LIST_TO_PG_MAP.items():
            groups = data.get(json_key, [])
            if not groups:
                logger.info(f"[migrate] {json_key} 为空，跳过")
                continue

            for group_id_str in groups:
                try:
                    group_id = int(group_id_str)
                except (ValueError, TypeError):
                    msg = f"无效的群号: {group_id_str} (列表: {json_key})"
                    logger.warning(f"[migrate] {msg}")
                    stats["errors"].append(msg)
                    continue

                for pg_name in pg_names:
                    pg = pg_map[pg_name]

                    # 检查是否已绑定
                    existing = await session.execute(
                        select(GroupPermBinding.id).where(
                            GroupPermBinding.qq_group_id == group_id,
                            GroupPermBinding.permission_group_id == pg.id,
                        )
                    )
                    if existing.first() is not None:
                        stats["skipped_existing"] += 1
                        continue

                    session.add(
                        GroupPermBinding(
                            qq_group_id=group_id,
                            permission_group_id=pg.id,
                        )
                    )
                    stats["migrated_groups"] += 1
                    logger.info(
                        f"[migrate] 群 {group_id} → 权限组 {pg_name} ({pg.display_name})"
                    )

        await session.commit()

    # 清除所有相关缓存
    perm_cache.clear_all()
    logger.info("[migrate] 已清除所有权限缓存")

    logger.info(
        f"[migrate] 迁移完成: 新增绑定 {stats['migrated_groups']}, "
        f"已存在 {stats['skipped_existing']}, 错误 {len(stats['errors'])}"
    )
    return stats


async def main():
    """手动运行迁移（用于测试）"""
    logging.basicConfig(level=logging.INFO)
    # 需要先加载配置（否则 JsonUtils 不知道数据目录）
    # 在 bot 环境中，这些已经由 nonebot 初始化。手动运行时需要额外设置。
    stats = await migrate_from_json()
    print(f"\n迁移结果: {stats}")


if __name__ == "__main__":
    asyncio.run(main())

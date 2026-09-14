# src/plugins/group_file_manager/migrations.py
"""表结构迁移（MySQL 方言，幂等）：

1. 给 monitored_groups 补 last_crawled_at 列
2. 把 group_files.group_id 的外键从 monitored_groups.id 重建为
   monitored_groups.group_id（带 ON DELETE CASCADE）

全部走 engine.connect() 裸连接（不走 session），避免 SQLAlchemy async
的 greenlet 嵌套冲突（MissingGreenlet）；DDL 在 MySQL 中隐式自动提交。
"""

import re

from sqlalchemy import text

from nonebot import logger

from .db import db_engine


async def _do_migrate_fk(conn, constraint_name: str) -> None:
    """执行 FK 迁移并验证结果。"""
    msg = f"[FK迁移] 开始迁移 FK `{constraint_name}`..."
    logger.warning(msg)
    print(msg)

    await conn.execute(text(
        f"ALTER TABLE group_files DROP FOREIGN KEY `{constraint_name}`"
    ))
    await conn.execute(text(
        f"ALTER TABLE group_files ADD CONSTRAINT `{constraint_name}` "
        f"FOREIGN KEY (`group_id`) REFERENCES `monitored_groups` (`group_id`) ON DELETE CASCADE"
    ))
    # DDL 在 MySQL 中自动提交，无需 conn.commit()
    # 且 async engine.connect() 的 connection 不支持 commit()

    # 验证迁移结果
    result = await conn.execute(text(
        "SELECT REFERENCED_COLUMN_NAME "
        "FROM INFORMATION_SCHEMA.KEY_COLUMN_USAGE "
        "WHERE TABLE_SCHEMA = DATABASE() "
        "  AND TABLE_NAME = 'group_files' "
        "  AND CONSTRAINT_NAME = :name"
    ), {"name": constraint_name})
    verify = result.fetchone()
    if verify and verify[0] == "group_id":
        msg = f"[FK迁移] 成功！FK `{constraint_name}` 已迁移到 monitored_groups.group_id"
        logger.info(msg)
        print(msg)
    else:
        actual = verify[0] if verify else "未知"
        msg = f"[FK迁移] 警告：迁移后验证失败，当前引用列: {actual}"
        logger.error(msg)
        print(msg)


async def _ensure_fk_migration() -> None:
    """自动检测并修复 group_files 表的外键约束。

    模型已改为 ForeignKey("monitored_groups.group_id")，但 MySQL 表结构可能
    仍指向 monitored_groups.id。此函数在插件启动时自动完成迁移，幂等安全。
    """
    msg = "[FK迁移] 开始检查 group_files 表的外键约束..."
    logger.info(msg)
    print(msg)  # print 兜底，确保 Docker logs 可见

    try:
        async with db_engine.connect() as conn:
            # 方法1：INFORMATION_SCHEMA 结构化查询
            result = await conn.execute(text(
                "SELECT CONSTRAINT_NAME, COLUMN_NAME, REFERENCED_COLUMN_NAME "
                "FROM INFORMATION_SCHEMA.KEY_COLUMN_USAGE "
                "WHERE TABLE_SCHEMA = DATABASE() "
                "  AND TABLE_NAME = 'group_files' "
                "  AND REFERENCED_TABLE_NAME = 'monitored_groups' "
                "  AND REFERENCED_COLUMN_NAME IS NOT NULL"
            ))
            row = result.fetchone()

            if row is None:
                msg = "[FK迁移] INFO_SCHEMA 未查到 FK，用 SHOW CREATE TABLE 复查..."
                logger.warning(msg)
                print(msg)
                # 方法2：SHOW CREATE TABLE 正则兜底
                result2 = await conn.execute(text("SHOW CREATE TABLE group_files"))
                create_row = result2.fetchone()
                if create_row:
                    ddl = create_row[1]
                    if "REFERENCES `monitored_groups` (`id`)" in ddl:
                        m = re.search(
                            r"CONSTRAINT `(\w+)` FOREIGN KEY.*"
                            r"REFERENCES `monitored_groups` \(`id`\)",
                            ddl
                        )
                        if m:
                            constraint_name = m.group(1)
                            logger.warning(
                                f"[FK迁移] SHOW CREATE TABLE 发现 FK `{constraint_name}` 指向 id"
                            )
                            await _do_migrate_fk(conn, constraint_name)
                            return
                    elif "REFERENCES `monitored_groups` (`group_id`)" in ddl:
                        logger.info("[FK迁移] SHOW CREATE TABLE 确认 FK 已指向 group_id，无需迁移")
                        return
                msg = "[FK迁移] 两种方法均未发现需修复的 FK，跳过"
                logger.info(msg)
                print(msg)
                return

            constraint_name = row[0]
            referenced_column = row[2]

            if referenced_column == "group_id":
                msg = f"[FK迁移] FK `{constraint_name}` 已指向 monitored_groups.group_id，无需迁移"
                logger.info(msg)
                print(msg)
                return

            logger.warning(
                f"[FK迁移] 检测到 FK `{constraint_name}` 指向 monitored_groups.{referenced_column}，"
                f"开始自动迁移到 monitored_groups.group_id..."
            )
            await _do_migrate_fk(conn, constraint_name)
    except Exception as e:
        msg = f"[FK迁移] 异常: {type(e).__name__}: {e}"
        logger.error(msg)
        print(msg)


async def _ensure_last_crawled_at_column() -> None:
    """自动检测并添加 monitored_groups.last_crawled_at 列（幂等安全）"""
    msg = "[初始化] 检查 monitored_groups.last_crawled_at 列..."
    logger.info(msg)
    print(msg)
    try:
        async with db_engine.connect() as conn:
            result = await conn.execute(text(
                "SELECT COUNT(*) FROM INFORMATION_SCHEMA.COLUMNS "
                "WHERE TABLE_SCHEMA = DATABASE() "
                "  AND TABLE_NAME = 'monitored_groups' "
                "  AND COLUMN_NAME = 'last_crawled_at'"
            ))
            count = result.scalar()
            if count == 0:
                logger.info("[初始化] 添加 last_crawled_at 列...")
                await conn.execute(text(
                    "ALTER TABLE monitored_groups "
                    "ADD COLUMN last_crawled_at DATETIME NULL DEFAULT NULL "
                    "AFTER is_active"
                ))
                logger.info("[初始化] last_crawled_at 列添加成功")
                print("[初始化] last_crawled_at 列添加成功")
            else:
                logger.info("[初始化] last_crawled_at 列已存在，跳过")
    except Exception as e:
        msg = f"[初始化] last_crawled_at 列迁移失败: {e}"
        logger.error(msg)
        print(msg)

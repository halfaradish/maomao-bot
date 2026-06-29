---
name: diting-db-guide
description: >
  DiTing-NoneBot Bot DB (diting_qq_bot) SQLAlchemy 操作指南。
  当需要操作数据库、定义模型、编写查询、使用 CRUD 包装器、添加新表、
  或排查数据库相关问题时使用。触发词：数据库、database、Bot DB、
  diting_qq_bot、SQLAlchemy、asyncmy、模型、model、CRUD、session、
  async_session_factory、查询、query、建表、过滤器、filter。
---

# DiTing Bot DB 数据库操作指南

> 针对 `diting_qq_bot`（Bot DB）数据库的 SQLAlchemy 2.0 async ORM 操作规范。

## 架构概览

```
环境变量 (.env / .env.{ENVIRONMENT})
  └─ BOT_DB_HOST, BOT_DB_USER, BOT_DB_PASSWORD, BOT_DB_NAME, BOT_DB_PORT, BOT_DB_POOL_SIZE
       │
       ▼
src/common/database.py
  ├─ engine          = create_async_engine("mysql+asyncmy://...")
  ├─ async_session_factory  = async_sessionmaker(engine, expire_on_commit=False)
  └─ Base            = DeclarativeBase  ← 所有 Bot DB 模型继承它
       │
       ▼
src/common/models/
  ├─ botdb_models.py        ← 12 个 Bot DB 表模型
  └─ like_plugin_models.py  ← 2 个 like 插件表模型
       │
       ▼
src/common/crud.py           ← 5 个异步 CRUD 包装函数（可选，封装了 session 管理）
```

| 组件 | 说明 |
|---|---|
| 驱动 | `asyncmy`（异步 MySQL） |
| 连接池 | `pool_pre_ping=True`, `pool_recycle=3600`, 池大小由 `BOT_DB_POOL_SIZE` 控制 |
| 会话 | `expire_on_commit=False`，允许 commit 后继续读取属性 |
| 基类 | `Base = DeclarativeBase`，所有 Bot DB 模型继承自它 |

**环境配置**：6 个 `BOT_DB_*` 环境变量在 `src/config/local_config.py` 的 `DiTingBotDBConfig` 中定义，每项都有默认值。`ENVIRONMENT` 变量决定加载哪个 `.env.{ENVIRONMENT}` 文件。参见 `env.template` 了解全部可用变量。

---

## 1. 获取会话

所有数据库操作的入口是 `async_session_factory()`：

```python
from src.common.database import async_session_factory
from sqlalchemy import select

async def example():
    async with async_session_factory() as session:
        result = await session.execute(select(SomeModel).where(...))
        data = result.scalars().all()
        # with 块正常结束时自动 commit
        # 发生异常时自动 rollback
```

**绝对不要**在模块顶层（插件导入时）创建会话：

```python
# ❌ 错误：插件 import 时就执行数据库查询
async with async_session_factory() as session:  # 报错！
    ...

# ✅ 正确：放在 async 函数/命令处理器内部
@cmd.handle()
async def handler():
    async with async_session_factory() as session:
        ...
```

---

## 2. 方式一：CRUD 包装函数（简单 CRUD 推荐）

`src/common/crud.py` 提供 5 个函数，封装了 session 管理，接口与旧 Django CRUD 一致：

### 2.1 创建 — `async_create_record`

```python
from src.common.crud import async_create_record
from src.common.models.botdb_models import TodoReminder
from datetime import datetime

obj = await async_create_record(
    TodoReminder,
    group_id=123456789,
    user_id=987654321,
    content="提醒内容",
    remind_time=datetime(2026, 7, 1, 9, 0),  # naive datetime
    remind_type="once",
    status="pending",
    created_by=987654321,
    last_modified_by=987654321,
)
# 返回已刷新到数据库的模型实例，包含自动生成的主键 obj.id
```

### 2.2 查询单条 — `async_get_one`

```python
from src.common.crud import async_get_one

# 精确匹配
reminder = await async_get_one(TodoReminder, id=42)
if reminder:
    print(reminder.content)

# 复合条件
msg = await async_get_one(QQRobotMessage, msg_seq=100, group_id=123456789)
```

### 2.3 查询多条 — `async_get_many`

```python
from src.common.crud import async_get_many

# 无条件全表
all_groups = await async_get_many(MonitoredGroup)

# 带过滤 + 排序 + 限制
rows = await async_get_many(
    TodoReminder,
    filters={"status": "pending", "remind_time__lte": datetime.now()},
    order_by=["remind_time"],      # 升序
    limit=100,
)

# 降序：字段前加 -
rows = await async_get_many(
    GroupFile,
    filters={"group_id": 123456789},
    order_by=["-downloaded_at"],   # 降序
)
```

### 2.4 更新 — `async_update_records`

```python
from src.common.crud import async_update_records

affected = await async_update_records(
    TodoReminder,
    filters={"id": 42},
    updates={"status": "completed", "executed_at": datetime.now()},
)
# 返回受影响的行数 (int)
```

### 2.5 删除 — `async_delete_records`

```python
from src.common.crud import async_delete_records

deleted = await async_delete_records(TodoReminder, id=42, user_id=123456)
# 返回删除的行数 (int)
```

**注意**：每个 CRUD 函数都独立打开/关闭 session。多个 CRUD 调用之间**不是同一个事务**——如果需要在同一个事务中执行多个操作，请使用直接 SQLAlchemy（第 4 节）。

---

## 3. 过滤器语法

CRUD 函数沿用 Django 风格的 `__` 查找后缀：

| 过滤器 | 含义 | 示例值 |
|---|---|---|
| `field=val` | 等于（默认） | `{"status": "pending"}` |
| `field__in=[a, b]` | 列表中 | `{"status__in": ["completed", "cancelled"]}` |
| `field__lte=val` | ≤ | `{"remind_time__lte": now}` |
| `field__lt=val` | < | `{"count__lt": 10}` |
| `field__gte=val` | ≥ | `{"count__gte": 5}` |
| `field__gt=val` | > | `{"advance_remind_minutes__gt": 0}` |
| `field__icontains=sub` | 不区分大小写包含 | `{"content__icontains": "比赛"}` |
| `field__contains=sub` | 区分大小写包含 | `{"name__contains": "test"}` |
| `field__startswith=pre` | 以...开头 | `{"name__startswith": "训练"}` |

### 3.1 关系遍历过滤器

支持通过 `__` 跨单跳关系查询（当前仅支持单跳）：

```python
from src.common.models.botdb_models import GroupMember

# 查询属于特定分组名的所有成员
# 等价于: GroupMember.group.has(Group.name.in_(["ACM", "OI"]))
members = await async_get_many(
    GroupMember,
    filters={"group__name__in": ["ACM", "OI"]},
)
```

多跳关系遍历会抛出 `NotImplementedError`。

---

## 4. 方式二：直接 SQLAlchemy 查询（复杂场景必须使用）

以下场景**必须**绕过 CRUD 包装器，使用直接 SQLAlchemy：

- JOIN + 聚合（`func.count`、`group_by`）
- 原子字段递增/递减（`Model.field + 1`）
- 预加载关系（`selectinload`，避免 N+1 查询）
- 同一事务中执行多个操作
- 复杂 WHERE 条件（`and_`/`or_`/`not_`）
- 原始 DDL（`ALTER TABLE` 等）

### 4.1 联表 + 聚合

```python
from sqlalchemy import func, select
from src.common.database import async_session_factory
from src.common.models.botdb_models import Group, GroupMember

async with async_session_factory() as session:
    stmt = (
        select(
            Group.name,
            Group.display_name,
            func.count(GroupMember.id).label("member_count"),
        )
        .outerjoin(Group.members)
        .group_by(Group.id)
        .order_by(Group.name)
    )
    result = await session.execute(stmt)
    rows = result.mappings().all()
    # 每行: {"name": ..., "display_name": ..., "member_count": ...}
```

### 4.2 预加载关系（Eager Loading）

```python
from sqlalchemy.orm import selectinload

async with async_session_factory() as session:
    stmt = (
        select(Group)
        .where(Group.name == "ACM")
        .options(selectinload(Group.members))
    )
    result = await session.execute(stmt)
    group = result.scalars().first()
    # group.members 已预加载，可直接遍历，不会触发额外 N+1 查询
    for member in group.members:
        print(member.qq_id, member.qq_nickname)
```

### 4.3 原子字段递增

```python
from sqlalchemy import update as sa_update

async with async_session_factory() as session:
    stmt = (
        sa_update(TodoReminder)
        .where(TodoReminder.id == reminder_id)
        .values(
            execution_count=TodoReminder.execution_count + 1,
            executed_at=datetime.now(),
            status="completed",
        )
    )
    await session.execute(stmt)
    await session.commit()
```

这和 Django 的 `F('execution_count') + 1` 效果相同，在数据库层面原子递增，避免并发竞争。

### 4.4 Update-or-Create 模式

```python
async with async_session_factory() as session:
    stmt = select(LikeRecord).where(LikeRecord.user_id == user_id)
    result = await session.execute(stmt)
    obj = result.scalars().first()

    if obj:
        # 更新已有记录 — 直接修改属性
        obj.nickname = nickname
        obj.is_following = True
    else:
        # 创建新记录
        obj = LikeRecord(user_id=user_id, nickname=nickname, is_following=True)
        session.add(obj)

    await session.commit()
```

### 4.5 通过 session.delete() 删除

```python
async with async_session_factory() as session:
    stmt = select(GroupStatistic).where(GroupStatistic.group_id == group_id)
    result = await session.execute(stmt)
    obj = result.scalars().first()
    if obj:
        await session.delete(obj)
        await session.commit()
```

另一种方式是 `sa_delete()` 语句（不需要先查询）：

```python
from sqlalchemy import delete as sa_delete

async with async_session_factory() as session:
    stmt = sa_delete(TodoReminder).where(
        TodoReminder.id == reminder_id,
        TodoReminder.user_id == user_id,
    )
    await session.execute(stmt)
    await session.commit()
```

---

## 5. 模式选择决策

| 场景 | 使用方式 | 理由 |
|---|---|---|
| 单表单条 CRUD | CRUD 包装函数 | 代码最简单 |
| 多条记录的简单查询/更新 | CRUD 包装函数 | 过滤器语法够用 |
| 需要在同一事务中执行多个操作 | 直接 SQLAlchemy | CRUD 每次是独立 session |
| 原子递增/递减 | 直接 SQLAlchemy | CRUD 不支持 `field = field + N` |
| JOIN / 聚合 / GROUP BY | 直接 SQLAlchemy | CRUD 不支持 |
| `selectinload` 预加载关系 | 直接 SQLAlchemy | CRUD 不支持 |
| 复杂 WHERE（`and_`/`or_`） | 直接 SQLAlchemy | CRUD 不支持 |
| 原始 DDL（`ALTER TABLE`） | 直接 SQLAlchemy `text()` | 唯一方式 |
| 关系遍历过滤（`group__name__in`） | CRUD 包装函数 | CRUD 已内置支持 |

**经验法则**：简单的增删改查用 CRUD，涉及"一起做多件事"或"SQL 表达式"时改用直接 SQLAlchemy。

---

## 6. 所有模型一览

### 6.1 botdb_models.py（12 个表）

| # | 模型类 | MySQL 表名 | 用途 | 主键 | 关键关系 |
|---|--------|-----------|------|------|---------|
| 1 | `MessageEventLog` | `messages_event_logs` | 消息事件日志 | `id` BigInt PK | 无 |
| 2 | `TodoReminder` | `todo_reminders` | 待办提醒 | `id` BigInt PK | → `TodoReminderLog` (cascade delete) |
| 3 | `TodoReminderLog` | `todo_reminder_logs` | 提醒执行日志 | `id` BigInt PK | → `TodoReminder` (FK to id) |
| 4 | `QQRobotMessage` | `qq_robot_messages` | 机器人发送的消息 | `id` String(32) UUID hex | → `QQMessageReaction` / `QQMessageReceiptSummary` / `QQMessageReminder` (cascade) |
| 5 | `QQMessageReaction` | `qq_message_reactions` | 消息表情回应 | `id` BigInt PK | → `QQRobotMessage` (FK CASCADE) |
| 6 | `QQMessageReceiptSummary` | `qq_message_receipt_summary` | 消息送达摘要 | `message_id` FK as PK | → `QQRobotMessage` (one-to-one, CASCADE) |
| 7 | `QQMessageReminder` | `qq_message_reminders` | 消息提醒规则 | `id` BigInt PK | → `QQRobotMessage` (FK CASCADE) |
| 8 | `Group` | `group` | 用户分组 | `id` BigInt PK, `name` UNIQUE | → `GroupMember` (FK to `group.name`, cascade) |
| 9 | `GroupMember` | `group_member` | 分组成员 | `id` BigInt PK | → `Group` (FK to name; unique on `group_name + qq_id`) |
| 10 | `MonitoredGroup` | `monitored_groups` | QQ 群监控列表 | `id` BigInt PK, `group_id` UNIQUE | → `GroupFile` (cascade) |
| 11 | `GroupFile` | `group_files` | 群文件记录 | `id` BigInt PK | → `MonitoredGroup` (FK to group_id; unique on `file_id + group_id`) |
| 12 | `GroupStatistic` | `group_statistics` | 群统计信息 | `id` BigInt PK, `group_id` UNIQUE | 无 |

### 6.2 like_plugin_models.py（2 个表）

| # | 模型类 | MySQL 表名 | 用途 | 主键 | 关键约束 |
|---|--------|-----------|------|------|---------|
| 13 | `LikeRecord` | `like_plugin_likerecord` | 点赞记录 | `user_id` String UNIQUE | `user_id` 即主键 |
| 14 | `PluginConfig` | `like_plugin_pluginconfig` | 插件 KV 配置 | `key` String UNIQUE | 键值存储模式 |

### 6.3 导入方式

模型通过 `src/common/models/__init__.py` 统一 re-export，推荐直接从 `__init__` 导入：

```python
# ✅ 推荐
from src.common.models.botdb_models import TodoReminder, Group
from src.common.models.like_plugin_models import LikeRecord, PluginConfig

# ✅ 也可以（如果 __init__ 有 re-export）
from src.common.models import TodoReminder, LikeRecord
```

---

## 7. 添加新表

### 步骤

**（1）定义模型** — 在 `src/common/models/botdb_models.py`（或新建文件）中添加：

```python
from sqlalchemy import BigInteger, DateTime, String, Text
from sqlalchemy.orm import Mapped, mapped_column
from datetime import datetime
from src.common.database import Base

class YourNewModel(Base):
    __tablename__ = "your_mysql_table_name"  # 必须与 MySQL 表名一致

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(100))
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.now)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.now, onupdate=datetime.now)
```

**（2）在 MySQL 中建表** — 直接执行 DDL 或通过代码：

```python
from src.common.database import engine, Base

async with engine.begin() as conn:
    await conn.run_sync(Base.metadata.create_all)
# 注意：这只会创建缺失的表，不会修改已有表
```

**（3）更新 `__init__.py`** — 在 `src/common/models/__init__.py` 中 re-export 新模型。

**（4）使用** — 通过 CRUD 或直接 SQLAlchemy：

```python
from src.common.models.botdb_models import YourNewModel
from src.common.crud import async_create_record, async_get_many

obj = await async_create_record(YourNewModel, name="test")
rows = await async_get_many(YourNewModel, filters={"name__icontains": "es"})
```

---

## 8. DateTime 处理

项目使用 **naive datetime**（无时区信息），时区约定为北京时间（Asia/Shanghai）：

```python
from datetime import datetime

# 创建时间（naive） — 直接使用
now = datetime.now()

# 模型中自动处理
# created_at: default=datetime.now          ← 创建时自动填充
# updated_at: default=datetime.now, onupdate=datetime.now  ← 创建+每次更新时自动填充
```

如果数据源可能传入带时区的 datetime，需要剥离 tzinfo（参考 `todo_reminder/database.py` 的实际实现）：

```python
def _ensure_naive_local(dt):
    """移除时区信息，转为 naive datetime（MySQL 兼容）"""
    if dt is None:
        return None
    if dt.tzinfo is not None and dt.tzinfo.utcoffset(dt) is not None:
        return dt.replace(tzinfo=None)
    return dt
```

---

## 9. 插件实战参考

以下是项目中每个插件使用的 DB 模式和技巧，可作为写新代码时的参考：

| 插件 | 模式 | 使用的模型 | 特色操作 |
|---|---|---|---|
| `ack_manager` | CRUD 全部 | QQRobotMessage, QQMessageReaction, QQMessageReceiptSummary, Group, GroupMember | 关系遍历过滤 (`group__name__in`)；update-or-create reaction/summary；消息状态机 |
| `todo_reminder` | **混合** (CRUD + 直接 SQLAlchemy) | TodoReminder, TodoReminderLog | 原子递增 (`execution_count + 1`)；复合条件删除 (`and_` + `in_`)；`_ensure_naive_local` |
| `like` | 直接 SQLAlchemy | LikeRecord, PluginConfig | 原子递增；对象属性直接修改后 commit；KV 配置存储；`@scheduler` 定时任务中使用 session |
| `logging_info` | CRUD 全部 | MessageEventLog | DAO 模式封装 CRUD；`__icontains` 搜索；北京时区转换 |
| `auto_manage_group` | 直接 SQLAlchemy | MessageEventLog | 时间范围查询 (`and_` + `>=` + `<=` + `!=`)；只在一个函数中使用 |
| `group_manager` | 直接 SQLAlchemy | Group, GroupMember | `func.count` + `outerjoin` + `group_by`；`selectinload` 预加载；`sa_delete`；存在性检查 |
| `group_file_manager` | 直接 SQLAlchemy | MonitoredGroup, GroupFile | 原始 DDL (`ALTER TABLE`)；FK 约束检测；session 作为函数参数传递；文件去重；`ENABLED` 条件导入 |
| `group_statistics` | 直接 SQLAlchemy | GroupStatistic | `session.delete()` 删除；独立 DAO 类；异常静默返回 False |

---

## 10. 常见陷阱

### 10.1 `metadata` 字段名冲突

SQLAlchemy 的 `Base` 保留了 `metadata` 属性名。如果表中正好有名为 `metadata` 的列，定义模型时需要重命名 Python 属性：

```python
# QQRobotMessage 中：DB 列名为 "metadata"，但 Python 属性用 metadata_
metadata_: Mapped[dict] = mapped_column("metadata", JSON, default=dict)
```

访问时用 `obj.metadata_`，写入 DB 的列名仍是 `metadata`。

### 10.2 UUID 主键用 hex 字符串

项目使用 **32 位 hex 字符串**（无横杠），对应 Django `UUIDField` 默认格式：

```python
id: Mapped[str] = mapped_column(
    String(32),
    primary_key=True,
    default=lambda: uuid.uuid4().hex
)
# 生成示例: "a1b2c3d4e5f6a7b8c9d0e1f2a3b4c5d6"
# 不是: "a1b2c3d4-e5f6-...-..." (不要用 str(uuid.uuid4()))
```

### 10.3 外键指向非主键列

`GroupMember.group_name` 的外键指向 `group.name`（不是 `group.id`），这是历史遗留设计：

```python
group_name: Mapped[str] = mapped_column(
    String(64), ForeignKey("group.name", ondelete="CASCADE")
)
```

新表不应模仿此模式——FK 应该指向目标表的主键。

### 10.4 不要在 session 外使用 ORM 对象的懒加载关系

```python
# ❌ 错误：在 async with 外访问关系属性可能失败（MissingGreenlet）
async with async_session_factory() as session:
    result = await session.execute(select(Group).where(...))
    group = result.scalars().first()
# ⚠️ 此处访问 group.members 可能触发懒加载 → 报错
for member in group.members:
    ...

# ✅ 正确：在会话内完成所有访问，或使用 selectinload 预加载
async with async_session_factory() as session:
    result = await session.execute(
        select(Group).where(...).options(selectinload(Group.members))
    )
    group = result.scalars().first()
    members = list(group.members)  # 在会话内转成普通 list
# 现在可以在会话外安全使用 members
```

### 10.5 查询返回类型对照

```python
result = await session.execute(stmt)

# 查询模型实例（select(Model)）
items = result.scalars().all()      # → List[Model]
item  = result.scalars().first()    # → Optional[Model]

# 查询特定列或聚合（select(col1, col2) / select(func.count(...))）
rows = result.mappings().all()      # → List[dict-like], 每行可 row["col_name"]
row  = result.mappings().first()    # → Optional[dict-like]
```

### 10.6 CRUD 调用之间不是同一事务

```python
# ⚠️ 这两步不在同一事务中！
await async_create_record(QQRobotMessage, ...)    # 独立 session — 已 commit
await async_create_record(QQMessageReceiptSummary, ...)  # 独立 session

# 如果第二步失败，第一步已经提交，无法回滚。
```

这种情况应改用直接 SQLAlchemy，在同一个 `async with` 块中完成，保证原子性。

### 10.7 `pymysql` 仅限 `llm_scribe`

整个代码库中，**只有** `llm_scribe` 插件还在使用 `pymysql`（独立的数据库连接，非 Bot DB）。所有 Bot DB 操作都已迁移到 SQLAlchemy async。不要在 Bot DB 相关代码中引入 `pymysql`。

---

## 11. 与 ICPC DB 的区别

这个项目有 **两套独立的数据库**，不要混淆：

| | Bot DB | ICPC DB |
|---|---|---|
| **环境变量前缀** | `BOT_DB_*` | `ICPC_DB_*` |
| **Session 工厂** | `src/common/database.py` → `async_session_factory` | `src/common/icpc_database.py` → `icpc_async_session_factory` |
| **Base 类** | `Base` | `IcpcBase` |
| **Models** | `src/common/models/botdb_models.py` + `like_plugin_models.py` | `src/common/models/icpc_models.py` |
| **兼容层** | 无 | `src/common/icpc_db_pool.py` → `get_icpc_db_connection()` 提供原始 SQL 查询 |
| **本指南适用范围** | ✅ 全部 | ❌ 不适用 |

ICPC DB 的操作方式不同：

```python
# ICPC DB 查询（通过原始 SQL 兼容层）
from src.common import get_icpc_db_connection

async with get_icpc_db_connection() as db:
    rows = await db.execute(
        "SELECT name, time FROM ding_checkup WHERE time >= %s",
        [start_time]
    )
    for row in rows:
        print(row["name"], row["time"])
```

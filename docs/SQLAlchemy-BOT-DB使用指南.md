# SQLAlchemy Bot DB 使用指南

本文档针对 DiTing-NoneBot 项目的 **Bot DB（谛听业务数据库）**，介绍如何用 SQLAlchemy 2.0 async ORM 进行数据库操作。

## 基本架构

```
src/common/
├── database.py          ← 引擎 + 会话工厂
├── crud.py              ← 异步 CRUD 包装层（5 个公开函数）
└── models/
    ├── botdb_models.py  ← 11 个 Bot DB 表模型
    └── like_plugin_models.py  ← 2 个 like 插件表模型
```

- **驱动**: `asyncmy`（异步 MySQL）
- **引擎**: `create_async_engine`，连接池配置来自 `BOT_DB_*` 环境变量
- **会话**: `async_session_factory`（`expire_on_commit=False`）
- **基类**: `Base = DeclarativeBase`，所有模型继承自它

---

## 1. 获取会话

所有数据库操作必须通过 `async_session_factory()` 获取异步会话：

```python
from src.common.database import async_session_factory
from sqlalchemy import select

async def example():
    async with async_session_factory() as session:
        result = await session.execute(select(SomeModel).where(...))
        data = result.scalars().all()
        # session 会在 with 块结束时自动 commit（如果没有异常）
        # 或 rollback（如果发生异常）
```

**关键点**:
- 使用 `async with` 确保会话正确关闭
- 不要在会话外使用 ORM 对象（`expire_on_commit=False` 允许在 commit 后继续读取属性，但不要跨请求持有对象）

---

## 2. 方式一：CRUD 包装函数（推荐）

`src/common/crud.py` 提供 5 个函数，接口与旧 Django CRUD 一致，内部自动管理会话：

### 2.1 创建记录 — `async_create_record`

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
# 返回已刷新的模型实例，包含自动生成的主键 obj.id
```

### 2.2 查询单条 — `async_get_one`

```python
from src.common.crud import async_get_one

# 精确匹配（默认 exact lookup）
reminder = await async_get_one(TodoReminder, id=42)
if reminder:
    print(reminder.content)

# 复合条件
record = await async_get_one(
    QQRobotMessage,
    msg_seq=100,
    group_id=123456789,
)
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
    order_by=["remind_time"],        # 升序
    limit=100,
)

# 降序排序 —— 字段前加 -
rows = await async_get_many(
    GroupFile,
    filters={"group_id": 123456789},
    order_by=["-downloaded_at"],     # 降序
)
```

### 2.4 更新记录 — `async_update_records`

```python
from src.common.crud import async_update_records

affected = await async_update_records(
    TodoReminder,
    filters={"id": 42},
    updates={"status": "completed", "executed_at": datetime.now()},
)
# 返回受影响的行数
```

### 2.5 删除记录 — `async_delete_records`

```python
from src.common.crud import async_delete_records

deleted = await async_delete_records(
    TodoReminder,
    id=42,
    user_id=123456,
)
# 返回删除的行数
```

---

## 3. 过滤器语法

CRUD 函数沿用 Django 风格的 `__` 查找后缀：

| 过滤器 | 含义 | 示例 |
|---|---|---|
| `field=val` | 等于（默认 `exact`） | `{"status": "pending"}` |
| `field__in=[...]` | 在列表中 | `{"status__in": ["completed", "cancelled"]}` |
| `field__lte=val` | ≤ | `{"remind_time__lte": now}` |
| `field__lt=val` | < | `{"count__lt": 10}` |
| `field__gte=val` | ≥ | `{"count__gte": 5}` |
| `field__gt=val` | > | `{"advance_remind_minutes__gt": 0}` |
| `field__icontains=sub` | 不区分大小写包含 | `{"content__icontains": "比赛"}` |
| `field__contains=sub` | 区分大小写包含 | `{"name__contains": "test"}` |
| `field__startswith=pre` | 以...开头 | `{"name__startswith": "训练"}` |

### 关系遍历过滤器

支持通过 `__` 跨关系查询（当前仅支持单跳关系）：

```python
from src.common.models.botdb_models import GroupMember

# 查询属于特定分组名的所有成员
# 等价于: GroupMember.group.has(Group.name.in_(["ACM", "OI"]))
members = await async_get_many(
    GroupMember,
    filters={"group__name__in": ["ACM", "OI"]},
)
```

---

## 4. 方式二：直接 SQLAlchemy 查询

对于复杂查询（JOIN、聚合、原子更新等），直接使用 SQLAlchemy 原生 API：

### 4.1 联表 + 聚合

```python
from sqlalchemy import func, select
from sqlalchemy.orm import selectinload
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
    stmt = select(Group).where(Group.name == "ACM").options(selectinload(Group.members))
    result = await session.execute(stmt)
    group = result.scalars().first()
    # group.members 已预加载，可直接遍历而不触发额外查询
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

这和 Django 的 `F('execution_count') + 1` 效果相同，在数据库层面原子递增。

### 4.4 条件更新（Update or Create）

```python
async with async_session_factory() as session:
    stmt = select(LikeRecord).where(LikeRecord.user_id == user_id)
    result = await session.execute(stmt)
    obj = result.scalars().first()

    if obj:
        # 更新已有记录
        obj.nickname = nickname
        obj.is_following = True
    else:
        # 创建新记录
        obj = LikeRecord(user_id=user_id, nickname=nickname, is_following=True)
        session.add(obj)

    await session.commit()
```

---

## 5. 所有模型一览

### botdb_models.py（11 个表）

| 模型 | 表名 | 用途 |
|---|---|---|
| `MessageEventLog` | `messages_event_logs` | 消息事件日志 |
| `TodoReminder` | `todo_reminders` | 待办提醒 |
| `TodoReminderLog` | `todo_reminder_logs` | 提醒执行日志 |
| `QQRobotMessage` | `qq_robot_messages` | 机器人发送的消息 |
| `QQMessageReaction` | `qq_message_reactions` | 消息表情回应 |
| `QQMessageReceiptSummary` | `qq_message_receipt_summary` | 消息送达摘要 |
| `QQMessageReminder` | `qq_message_reminders` | 消息提醒规则 |
| `Group` | `group` | 用户分组 |
| `GroupMember` | `group_member` | 分组成员 |
| `MonitoredGroup` | `monitored_groups` | QQ 群监控列表 |
| `GroupFile` | `group_files` | 群文件记录 |

### like_plugin_models.py（2 个表）

| 模型 | 表名 | 用途 |
|---|---|---|
| `LikeRecord` | `like_plugin_likerecord` | 点赞记录 |
| `PluginConfig` | `like_plugin_pluginconfig` | 插件配置（KV 存储） |

---

## 6. 添加新表

### 步骤

**（1）定义模型** — 在 `src/common/models/` 下添加：

```python
# src/common/models/botdb_models.py (或新建文件)
from sqlalchemy import BigInteger, DateTime, String
from sqlalchemy.orm import Mapped, mapped_column
from datetime import datetime
from src.common.database import Base

class YourNewModel(Base):
    __tablename__ = "your_mysql_table_name"  # 必须与 MySQL 表名一致

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(100))
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.now)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.now, onupdate=datetime.now)
```

**（2）创建 MySQL 表** — 直接在数据库中建表，或通过代码：

```python
from src.common.database import engine, Base
# 注意：这会创建所有缺失的表，不会修改已有表
async with engine.begin() as conn:
    await conn.run_sync(Base.metadata.create_all)
```

**（3）使用** — 通过 CRUD 包装函数或直接 SQLAlchemy 查询：

```python
from src.common.models.botdb_models import YourNewModel
from src.common.crud import async_create_record, async_get_many

obj = await async_create_record(YourNewModel, name="test")
rows = await async_get_many(YourNewModel, filters={"name__icontains": "es"})
```

---

## 7. DateTime 处理

项目使用 **naive datetime**（无时区信息），时区约定为北京时间（Asia/Shanghai）：

```python
from datetime import datetime

# 当前时间（naive）
now = datetime.now()

# 创建时直接使用
reminder = await async_create_record(
    TodoReminder,
    remind_time=datetime(2026, 7, 1, 9, 0),  # 无 tzinfo
    ...
)

# 模型中自动处理
# created_at: default=datetime.now          ← 创建时自动填充
# updated_at: default=datetime.now, onupdate=datetime.now  ← 创建+更新时自动填充
```

**如果传入了带时区的 datetime**，需要去掉 tzinfo：

```python
def _ensure_naive_local(dt):
    """移除时区信息，转为 naive datetime"""
    if dt is None:
        return None
    if dt.tzinfo is not None and dt.tzinfo.utcoffset(dt) is not None:
        return dt.replace(tzinfo=None)
    return dt
```

---

## 8. 注意事项

### 8.1 `metadata` 字段名冲突

SQLAlchemy 的 `DeclarativeBase` 保留了 `metadata` 属性名。如果表中恰好有名为 `metadata` 的列，模型定义时需要重命名 Python 属性：

```python
# QQRobotMessage 中：数据库列名为 "metadata"，但 Python 属性用 metadata_
metadata_: Mapped[dict] = mapped_column("metadata", JSON, default=dict)
```

访问时使用 `obj.metadata_`，写入数据库列名仍是 `metadata`。

### 8.2 UUID 主键格式

项目使用 **32 位 hex 字符串**（无横杠），对应 Django 的 `UUIDField` 默认格式：

```python
id: Mapped[str] = mapped_column(
    String(32), primary_key=True, default=lambda: uuid.uuid4().hex
)
# 生成示例: "a1b2c3d4e5f6a7b8c9d0e1f2a3b4c5d6"
# 不是: "a1b2c3d4-e5f6-...-..." (不用 str(uuid.uuid4()))
```

### 8.3 外键指向非主键列

`GroupMember.group_name` 的外键指向 `group.name`（不是 `group.id`）：

```python
group_name: Mapped[str] = mapped_column(
    String(64), ForeignKey("group.name", ondelete="CASCADE")
)
```

这是从 Django `to_field='name'` 迁移过来的历史设计，新表不应模仿。

### 8.4 不要在会话外使用 ORM 对象

```python
# ❌ 错误：在 async with 外访问关系属性可能触发懒加载，导致 MissingGreenlet 错误
async with async_session_factory() as session:
    result = await session.execute(select(Group).where(...))
    group = result.scalars().first()
# ⚠️ 此处访问 group.members 可能失败
for member in group.members:  # 可能报错
    ...

# ✅ 正确：在会话内完成所有访问，或使用 selectinload 预加载
async with async_session_factory() as session:
    result = await session.execute(
        select(Group).where(...).options(selectinload(Group.members))
    )
    group = result.scalars().first()
    members = list(group.members)  # 在会话内转换为普通列表

# 现在可以在会话外使用 members 了
for member in members:
    ...
```

### 8.5 查询返回类型

```python
result = await session.execute(stmt)

# 查询模型实例（select(Model)）
items = result.scalars().all()      # List[Model]
item = result.scalars().first()     # Optional[Model]

# 查询特定列或聚合（select(col1, col2)）
rows = result.mappings().all()      # List[dict-like]
row = result.mappings().first()     # Optional[dict-like]
```

### 8.6 不要在插件顶层创建会话

```python
# ❌ 错误：插件导入时就直接执行数据库操作
from src.common.database import async_session_factory
async with async_session_factory() as session:  # 报错！
    ...

# ✅ 正确：放在异步函数/命令处理器中
@my_command.handle()
async def handler():
    async with async_session_factory() as session:
        ...
```

---

## 9. 与 ICPC DB 的区别

这个项目有 **两套独立的数据库**，不要混淆：

| | Bot DB | ICPC DB |
|---|---|---|
| **环境变量前缀** | `BOT_DB_*` | `ICPC_DB_*` |
| **驱动** | `asyncmy`（异步） | `asyncmy`（异步） |
| **ORM** | SQLAlchemy 2.0 async | SQLAlchemy 2.0 async（原始 SQL via `text()`） |
| **接入方式** | `async_session_factory` | `get_icpc_db_connection()`（async） |
| **Session Factory** | `src/common/database.py` | `src/common/icpc_database.py` |
| **Models** | `src/common/models/botdb_models.py` | `src/common/models/icpc_models.py` |
| **本指南适用范围** | ✅ | ✅（接入方式相同，均为 async SQLAlchemy） |

### ICPC DB 使用示例

```python
from src.common import get_icpc_db_connection

async def example():
    async with get_icpc_db_connection() as db:
        # execute() 自动将 %s 转为 :N 占位符，返回 list[dict]
        rows = await db.execute("SELECT name, time FROM ding_checkup WHERE time >= %s", [start_time])
        for row in rows:
            print(row["name"], row["time"])
```

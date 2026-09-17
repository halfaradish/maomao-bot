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
  ├─ like_plugin_models.py  ← 2 个 like 插件表模型
  ├─ plugin_usage_models.py / vv_models.py  ← 插件专属模型文件
  └─ duel/fakemsg/mass_kick/prd/shit_transport_models.py
                            ← 原 JSON 存储插件迁移后的模型（均含 env_tag 隔离列）
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

**推荐入口是 `get_session()`**（自动 commit/rollback/关闭）：

```python
from src.common.database import get_session
from sqlalchemy import select

async def example():
    async with get_session() as session:        # 退出时自动 commit，异常时 rollback 并抛出
        result = await session.execute(select(SomeModel).where(...))
        data = result.scalars().all()

async def read_only_example():
    async with get_session(commit=False) as session:   # 纯读取：不提交
        ...
```

仍可直接使用 `async_session_factory()`（自管 commit/rollback，**不再自动提交**），但**新代码一律走 `get_session()`**；存量裸工厂调用点已清零（只剩工厂定义处、ICPC 池、以及 `api/bot.py` 那个刻意参数化的探针，见 §1.2）。

### 1.1 两条硬规则

**规则一：`finish()` 等一切「会抛异常的收尾」必须放在会话块之外。**

`get_session()` 在块内异常退出时先 rollback 再重抛，而 nonebot 的 `matcher.finish()` 抛的正是 `FinishedException`。写在块内会让同块里刚写入的数据**静默回滚**，用户却收到成功提示：

```python
# ❌ finish() 在块内：绑定写进去又被回滚，用户却看到「已添加」
async with get_session() as session:
    session.add(GroupPermBinding(...))
    await matcher.finish("已添加")        # 抛 FinishedException → rollback

# ✅ 块内只做 DB，块外统一 finish
async with get_session() as session:
    session.add(GroupPermBinding(...))
await matcher.finish("已添加")            # 退出块时已 commit
```

辅助函数同理：`await helper()` 里若可能走到 `finish()`，该 helper 必须在会话块外调用。反过来说，**不要跨网络调用持有 session**——`finish()`/`bot.send()` 都该在块外。

正例：`group_file_manager/handlers.py` 的 `handle_add_monitor` 把 `bot.get_group_info()` 挪到会话块之前，块内只留查/写；`handle_crawl` 的 `crawl_group_files()` 也只在块外调用。

（历史案例：`group_file_manager/handlers.py` 曾因此必须在 `finish()` 前显式补一次 `commit()`——该文件已在 2025-09 的整段重排里改成「块内只做 DB、`finish` 出块」，见 §1.2。）

**规则二：纯读取用 `commit=False`。**

只读块若用默认的 `commit=True`，退出时会多发一次无意义的 COMMIT；更要紧的是它把「这个块不会写」这一意图显式化了。反过来，**块内存在「查到就写、查不到就不写」分支时用默认 `commit=True`**，让未命中分支也走一次空提交，与改造前行为一致。

### 1.2 会话入口迁移状态

| 状态 | 文件数 | 站点数 |
|---|---|---|
| 已用 `get_session()` | 43 | 146 |
| 仍用裸 `async_session_factory()` | 0 | 0 |

（口径：`get_session(` **调用点**，含 `scripts/`；其中 `commit=False` 共 **59** 处——只统计值确实为 `False` 的调用点，另有 1 处显式写 `commit=True`。想复核就按「AST 里 `get_session` 调用 + `commit` 关键字取值为 `False`」来数，别用 `grep commit=False`，那个会把注释和 docstring 一起算进去。）

**裸工厂只剩 3 处引用，都不是待迁移的遗留**：
- `common/database.py` —— 工厂定义处（`get_session()` 自己就建在它上面）；
- `common/icpc_db_pool.py` —— ICPC 库的连接池，与 bot_db 无关；
- `api/bot.py` 的 `_ping_mysql(session_factory)` —— 刻意收工厂当参数，好让同一个探针同时服务 bot_db 与 ICPC 库。

**会话块内 `finish()` 已清零**（全仓库 0 处）。`group_file_manager/handlers.py` 原先那 8 处已按 §1.3 的办法整段重排：块内只查/写并把文案记进 `msg` 变量，`finish()` 一律移到块外。顺带把 `handle_add_monitor` 的 `bot.get_group_info()`（网络调用）也挪出了会话块。

**会话块内显式 `commit()` 只剩 4 处，都可以留，但理由各不相同**：

| 位置 | 类型 | 理由 |
|---|---|---|
| `group_file_manager/handlers.py` `handle_group_upload` | 词法块内 | 先把新群落库，再下载文件；下载失败回滚时不能连带丢掉群记录 |
| `group_file_manager/hooks.py` `init_monitored_groups` | 词法块内 | 必须在 `auto_crawl` 之前提交，否则其独立会话看不到新群行 |
| `group_file_manager/service.py` `download_and_save`（由 `handle_group_upload` 传入同一个 session） | 语义块内 | 下载成功后的落库提交；与上一条同一事务 |
| `auto_manage_group/migrate.py` `_ensure_permission_groups` | 语义块内 | 建权限组后要立刻提交，后续步骤依赖它已可见 |

前两处**词法上**落在 `async with get_session()` 里（静态闸按 `文件::函数` 白名单校验）；后两处是**语义上**的块内提交——它们只收到一个 `session` 参数，看不出身边有 `get_session`，静态闸抓不到，改的时候要自己认。四处所在块内都**没有** `finish()`，所以不构成 §1.1 规则一那种「写完又被回滚」的风险；要动它们必须同时确认上面那条语义。

**另外一处**已知违背「块内只做 DB」：`handle_group_upload` 仍在同一个块内调 `bot.get_group_info()` 与 `download_and_save()`（后者本来就是下载 + 落库，块刻意持有事务边界以保证「新群先落库」）。这是**有意保留**的例外，不是遗漏；想拆的话要连着上面第一条语义一起重排。

### 1.3 改 `finish()` 在块内的 handler：只记标志，出块再提示

`permission_manager` / `vv` / `fakemsg` 这类「先查重、重复就提示、否则写入」的 handler，原先把 `finish()` 写在块内。改造时把提前返回的分支改成**记一个布尔标志**，提示统一挪到块外：

```python
# ❌ finish() 在块内：判重分支会把块里刚 add 的数据一起回滚掉
async with get_session() as session:
    if (await session.execute(...)).first() is not None:
        await matcher.finish("已存在")

# ✅ 标志 + 出块提示
exists = False
async with get_session() as session:
    if (await session.execute(...)).first() is not None:
        exists = True
    else:
        session.add(obj)
if exists:
    await matcher.finish("已存在")
```

一个必须守住的细节：**「命中重复」这个提前返回分支上不能有已 staged 的写**。绝大多数站点天然满足（判重在写之前），但也有反例——`fakemsg/core.py` 的 `-add` 会在判重之前先建权限组+flush，只是「组刚建好就已是成员」在数据上不可能发生，才没暴露。搬 `finish` 时顺手确认一下这点。

另有一处控制流细节：`view.py` 的「黑名单命中就跳过白名单/权限组查询」是靠 `if bl: ... finish()` 提前返回实现的，`finish` 外提后必须补成 `if not blacklisted:` 把后半段包起来，否则黑名单用户的消息里会多出一行「无任何权限（默认拒绝）」。

### 1.4 改 「`add` + `commit`」时当心主键

`session.commit()` 会顺带 flush，所以 `session.add(obj)` → `commit()` → `obj.id` 这种写法里，**`commit()` 同时承担了「拿到自增主键」的职责**。只把 commit 换成块退出的自动提交、却不补 flush，`obj.id` 就会是 `None`，接口静默返回 `"id": null`：

```python
# ❌ 只删 commit：group.id 还没被 flush 出来
session.add(group)
group_id = group.id                    # → None

# ✅ 需要主键时显式 flush，提交交给 get_session()
session.add(group)
await session.flush()
group_id = group.id
```

既有正例：`api/groups.py` 的 toggle 分支、`common/permission/bootstrap.py` 本来就是这个写法。

### 1.5 删「行尾 commit」时的两个顺序变化

块**中间/trailing** 的 `await session.commit()` 删掉后，提交时点从「那一行」挪到「出块时」，于是它后面的非 DB 代码会提前到提交之前执行。两种常见情形都无害，但要知道自己在做什么：

1. **先清缓存、再提交**：如 `vv`、`fakemsg`、`shit_transport` 的 `perm_cache.clear_pattern()/clear_all()`。提前清缓存是安全方向（宁可多失效一次），提交失败时也只是多清一次。
2. **先记日志、再提交**：日志会比落库早一点点出现。`_ensure_*_perm_group` 这类启动钩子里会看到日志打了但（极端情况下）没落库。

判断标准：这段代码**读不读刚写的数据**。读就得保留显式 commit（或至少 flush），不读就可以交给块退出。


**绝对不要**在模块顶层（插件导入时）创建会话：

```python
# ❌ 错误：插件 import 时就执行数据库查询
async with get_session() as session:  # 报错！
    ...

# ✅ 正确：放在 async 函数/命令处理器内部
@cmd.handle()
async def handler():
    async with get_session() as session:
        ...
```

**建表**：用 `ensure_tables(*models)`（幂等，只建传入模型对应的表）：

```python
from src.common.database import ensure_tables

@get_driver().on_startup
async def _create_tables():
    await ensure_tables(MyModelA, MyModelB)
```

`permission/auto_register.py` 启动时会额外做一次全量建表（创建 Base 上全部已注册模型的缺失表）。

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

**注意**：每个 CRUD 函数默认独立提交，且**数据库错误会原样抛出**（不会转换为 None/[]/0）——需要降级语义时自行 try/except。所有函数都接受关键字参数 `session=`：传入一个会话即可把多个 CRUD 调用组成同一事务（此时不提交，由外层 `get_session()` 统一提交）：

```python
from src.common.database import get_session
from src.common.crud import async_create_record, async_update_records

async def composed():
    async with get_session() as session:
        obj = await async_create_record(SomeModel, session=session, name="x")
        await async_update_records(OtherModel, {"id": 1}, {"ref": obj.id}, session=session)
    # with 退出时统一提交；任一步抛异常则整体回滚
```

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
from src.common.database import get_session
from src.common.models.botdb_models import Group, GroupMember

async with get_session(commit=False) as session:      # 纯读取
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

async with get_session(commit=False) as session:      # 纯读取
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

async with get_session() as session:
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
    # 退出块时自动 commit，无需显式写法
```

这和 Django 的 `F('execution_count') + 1` 效果相同，在数据库层面原子递增，避免并发竞争。

### 4.4 Update-or-Create 模式

```python
async with get_session() as session:
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
    # 退出块时统一提交
```

### 4.5 通过 session.delete() 删除

```python
async with get_session() as session:
    stmt = select(GroupStatistic).where(GroupStatistic.group_id == group_id)
    result = await session.execute(stmt)
    obj = result.scalars().first()
    if obj:
        await session.delete(obj)
```

另一种方式是 `sa_delete()` 语句（不需要先查询）：

```python
from sqlalchemy import delete as sa_delete

async with get_session() as session:
    stmt = sa_delete(TodoReminder).where(
        TodoReminder.id == reminder_id,
        TodoReminder.user_id == user_id,
    )
    result = await session.execute(stmt)
    # result.rowcount 在 with 块内取，块退出后即为已提交状态
    deleted = result.rowcount
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

### 6.1 botdb_models.py（13 个表）

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
| 13 | `CustomHoliday` | `custom_holiday` | 自定义节假日（覆盖 API 数据） | `id` BigInt PK, `date` UNIQUE | 无 |

### 6.2 like_plugin_models.py（2 个表）

| # | 模型类 | MySQL 表名 | 用途 | 主键 | 关键约束 |
|---|--------|-----------|------|------|---------|
| 13 | `LikeRecord` | `like_plugin_likerecord` | 点赞记录 | `user_id` String UNIQUE | `user_id` 即主键 |
| 14 | `PluginConfig` | `like_plugin_pluginconfig` | 插件 KV 配置 | `key` String UNIQUE | 键值存储模式 |

### 6.3 原 JSON 存储插件模型（2026-09 由 data/*.json 迁入，均含 `env_tag` 隔离列）

这些表来自 5 个原使用 `JsonUtils` JSON 文件存储的插件，数据由
`scripts/migrate_json_to_db.py`（幂等，`--archive` 归档源文件）一次性迁入。
env_tag 的取值来源、DAO 过滤模式与按 id 校验规范，见第 7 节「env_tag 环境隔离约定」。

| 模型类（文件） | MySQL 表名 | 来源 JSON | 说明 |
|---|---|---|---|
| `DuelStandardTag`（duel_models.py） | `duel_tags` | duel.json `map` 键 | CF 标准标签词表，`UNIQUE(env_tag, tag)` |
| `DuelTagAlias`（duel_models.py） | `duel_tag_aliases` | duel.json `map`/`quick_map` | 标签别名，`UNIQUE(env_tag, alias)`（原双向冗余消失） |
| `DuelDailyProblemState`（duel_models.py） | `duel_daily_problem_state` | duel.json `daily_problems` | 每环境单行，`history` 为 JSON 列（字符串题号） |
| `FakemsgDailyUsage`（fakemsg_models.py） | `fakemsg_daily_usage` | fakemsg.json `daily_times_log` | 按 `(env_tag, user_id, usage_date)` 唯一，旧 `last_refresh_date` 键由 usage_date 取代 |
| `MassKickManagedGroup`（mass_kick_models.py） | `mass_kick_managed_groups` | mass_kick.json `managed_groups` | `UNIQUE(env_tag, group_id)` |
| `PrdTodo`（prd_models.py） | `prd_todos` | prd.json `to_do` | 编号即自增主键（迁移保留原编号）；`group` 为 MySQL 保留字，属性名 `group_name`；`prd_exist_groups` 改为插件配置 |
| `ShitTransportStats`（shit_transport_models.py） | `shit_transport_stats` | shit_transport.json 两个统计 dict | `kind` = banshi/postshi，`UNIQUE(env_tag, user_id, kind)` |

对应 DAO 层在各插件目录 `dao.py`（模块级异步函数），参考 `plugin_usage_stats/dao.py` 的分层模式。

### 6.4 导入方式

模型通过 `src/common/models/__init__.py` 统一 re-export，推荐直接从 `__init__` 导入：

```python
# ✅ 推荐
from src.common.models.botdb_models import TodoReminder, Group
from src.common.models.like_plugin_models import LikeRecord, PluginConfig

# ✅ 也可以（如果 __init__ 有 re-export）
from src.common.models import TodoReminder, LikeRecord
```

---

## 7. env_tag 环境隔离约定

同一 MySQL 库（`diting_qq_bot`）会被多个环境实例共用（prod/dev/local/docker，由 `.env` 的 `ENVIRONMENT` 决定）。`env_tag` 列标记每行数据的归属环境，防止 dev 测试数据混入 prod、或 dev 环境误改 prod 数据。

> 列宽口径：`String(20)`（现有 8 张表一致：duel 3 张 + fakemsg + mass_kick + plugin_usage_stats + prd + shit_transport）。早期设计文档写的 `VARCHAR(32)` 已废弃，以本节为准。

### 7.1 取值来源 — 只用 `current_env_tag()`

```python
from src.common.database import current_env_tag
```

- **bot 运行时**：读 nonebot 配置 `config.environment`（即 `.env` 的 `ENVIRONMENT`）
- **独立脚本**（未 `nonebot.init()`）：回退读 `ENVIRONMENT` 环境变量，缺省 `dev`

**禁止**在插件/DAO 中自行读环境（`get_driver().config.environment`、`os.getenv("ENVIRONMENT")` 等）——统一走 `current_env_tag()`，保证打标与过滤口径一致。

### 7.2 标准列定义

`env_tag` 紧跟 `id` 之后，`String(20)`；复合 UNIQUE / INDEX 一律以 env_tag 为首位：

```python
from sqlalchemy import BigInteger, Index, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column
from src.common.database import Base

class YourNewModel(Base):
    __tablename__ = "your_mysql_table_name"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    env_tag: Mapped[str] = mapped_column(String(20))
    # ... 业务字段 ...

    __table_args__ = (
        UniqueConstraint("env_tag", "user_id", name="uq_your_table_env_user"),
        # 或 Index("idx_your_table_env_xxx", "env_tag", "..."),
    )
```

### 7.3 DAO 读写模式

**写入**：插入时显式打标（参考 `plugin_usage_stats/dao.py`）：

```python
session.add(PluginUsageRecord(
    module_name=module_name,
    env_tag=current_env_tag(),   # ← 显式打标
    ...
))
```

**查询/更新/删除**：每条 where 都带环境过滤：

```python
stmt = stmt.where(PluginUsageRecord.env_tag == current_env_tag())
```

**按自增 id 读写必须校验 env_tag**（自增主键跨环境共享序列，防止 dev 误改 prod），参考 `prd/dao.py`：

```python
async with get_session() as session:      # 查到才写，用默认 commit=True
    row = await session.get(PrdTodo, todo_id)
    if row is None or row.env_tag != current_env_tag():
        # 未命中：返回前块会走一次空提交（与显式 commit 的旧写法行为一致）
        return None              # 不是本环境的数据，视同不存在
    # ... 修改，退出块时统一 commit ...
```

### 7.4 适用边界 — 默认必加 + 豁免清单

**所有 Bot DB 新表默认必加 `env_tag`。** 拿不准就加——忘加的代价（dev/prod 数据串）远大于多一列。

| 判定 | 数据类别 | 例子 |
|---|---|---|
| ✅ 必加 | 每个环境有独立语义的插件私有数据 | 每日额度、标签词表、需求待办、管理名单、使用统计 |
| ⛔ 可豁免 | 纯全局共享数据（跨环境本就应共享同一份） | 用户分组、平台级只读配置 |

豁免时删掉 env_tag 列，并在模型 docstring 中写明豁免理由。

**现有豁免清单**（历史表，维持现状，不回溯加列）：

- `botdb_models.py` 全部 13 张、`like_plugin_models.py` 2 张、`vv_models.py`
- ICPC 库整体不适用（独立数据库，不存在同库多环境问题）

---

## 8. 添加新表

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
    env_tag: Mapped[str] = mapped_column(String(20))  # 默认必加，见第 7 节
    name: Mapped[str] = mapped_column(String(100))
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.now)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.now, onupdate=datetime.now)
```

> **env_tag 豁免确认**：新表默认必加 `env_tag`（模板已含）。只有纯全局共享数据才可豁免——删掉该列并在模型 docstring 写明理由。判定标准、列定义与 DAO 过滤模式见第 7 节「env_tag 环境隔离约定」。

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

## 9. DateTime 处理

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

## 10. 插件实战参考

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
| `plugin_usage_stats` | 直接 SQLAlchemy | PluginUsageRecord | DAO 模块级异步函数分层；`env_tag` 环境隔离；热路径异常吞掉不阻断消息 |
| `mass_kick` / `shit_transport` / `fakemsg` / `duel` / `prd` | 直接 SQLAlchemy | 各自 `*_models.py`（见 6.3） | 由 JSON 存储迁移而来；MySQL upsert（`mysql_insert.on_duplicate_key_update`）做原子计数；DAO 返回 legacy dict 保持旧字段形状 |
| `group_card_changer` | 直接 SQLAlchemy | CustomHoliday | 只读加载自定义节假日覆盖 API 数据；DB 失败降级为「仅用 API 数据」 |
| `vv` / `group_sentinel` / `diting_deploy` | 直接 SQLAlchemy | VvGroupBlacklist / PermissionGroup 系列 | 专属黑名单 + 权限组播种；启动钩子里 `add + flush` 后由块退出提交 |

> 这张表是**示例**而非清单——以 `src/plugins/` 目录为准；`api/` 下 9 个模块与 `common/permission/*` 也都走 `get_session()`。

---

## 11. 常见陷阱

### 11.1 `metadata` 字段名冲突

SQLAlchemy 的 `Base` 保留了 `metadata` 属性名。如果表中正好有名为 `metadata` 的列，定义模型时需要重命名 Python 属性：

```python
# QQRobotMessage 中：DB 列名为 "metadata"，但 Python 属性用 metadata_
metadata_: Mapped[dict] = mapped_column("metadata", JSON, default=dict)
```

访问时用 `obj.metadata_`，写入 DB 的列名仍是 `metadata`。

### 11.2 UUID 主键用 hex 字符串

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

### 11.3 外键指向非主键列

`GroupMember.group_name` 的外键指向 `group.name`（不是 `group.id`），这是历史遗留设计：

```python
group_name: Mapped[str] = mapped_column(
    String(64), ForeignKey("group.name", ondelete="CASCADE")
)
```

新表不应模仿此模式——FK 应该指向目标表的主键。

### 11.4 不要在 session 外使用 ORM 对象的懒加载关系

```python
# ❌ 错误：在 async with 外访问关系属性可能失败（MissingGreenlet）
async with get_session(commit=False) as session:
    result = await session.execute(select(Group).where(...))
    group = result.scalars().first()
# ⚠️ 此处访问 group.members 可能触发懒加载 → 报错
for member in group.members:
    ...

# ✅ 正确：在会话内完成所有访问，或使用 selectinload 预加载
async with get_session(commit=False) as session:
    result = await session.execute(
        select(Group).where(...).options(selectinload(Group.members))
    )
    group = result.scalars().first()
    members = list(group.members)  # 在会话内转成普通 list
# 现在可以在会话外安全使用 members
```

### 11.5 查询返回类型对照

```python
result = await session.execute(stmt)

# 查询模型实例（select(Model)）
items = result.scalars().all()      # → List[Model]
item  = result.scalars().first()    # → Optional[Model]

# 查询特定列或聚合（select(col1, col2) / select(func.count(...))）
rows = result.mappings().all()      # → List[dict-like], 每行可 row["col_name"]
row  = result.mappings().first()    # → Optional[dict-like]
```

### 11.6 CRUD 调用之间不是同一事务

```python
# ⚠️ 这两步不在同一事务中！
await async_create_record(QQRobotMessage, ...)    # 独立 session — 已 commit
await async_create_record(QQMessageReceiptSummary, ...)  # 独立 session

# 如果第二步失败，第一步已经提交，无法回滚。
```

这种情况应改用直接 SQLAlchemy，在同一个 `async with` 块中完成，保证原子性。

### 11.7 `pymysql` 仅限 `llm_scribe`

整个代码库中，**只有** `llm_scribe` 插件还在使用 `pymysql`（独立的数据库连接，非 Bot DB）。所有 Bot DB 操作都已迁移到 SQLAlchemy async。不要在 Bot DB 相关代码中引入 `pymysql`。

### 11.8 `finish()` 写在 `get_session()` 块内会静默回滚

最常见也最隐蔽的一个坑：`matcher.finish()` 抛 `FinishedException`，被 `get_session()` 当成异常 → rollback。结果是**数据没写进去，用户却收到成功提示**。

```python
# ❌ 用户看到「已添加」，但绑定已被回滚
async with get_session() as session:
    session.add(GroupPermBinding(...))
    await matcher.finish("已添加")

# ✅ 块内只做 DB，块外统一 finish
async with get_session() as session:
    session.add(GroupPermBinding(...))
await matcher.finish("已添加")
```

判断口诀：**块内只碰 DB，`finish()`/`send()` 一律在块外。** 详见 §1.1 规则一。

---

## 12. 与 ICPC DB 的区别

这个项目有 **两套独立的数据库**，不要混淆：

| | Bot DB | ICPC DB |
|---|---|---|
| **环境变量前缀** | `BOT_DB_*` | `ICPC_DB_*` |
| **Session 入口** | `src/common/database.py` → `get_session(*, commit=True)`（裸 `async_session_factory` 仅底层工厂自用） | `src/common/icpc_database.py` → `icpc_async_session_factory` |
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

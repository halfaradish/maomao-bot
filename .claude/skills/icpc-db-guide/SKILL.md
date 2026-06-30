---
name: icpc-db-guide
description: >
  DiTing-NoneBot ICPC DB (竞赛数据库) 操作指南。
  当需要操作 ICPC 竞赛数据库、编写原始 SQL 查询、使用 get_icpc_db_connection、
  排查 ICPC DB 查询问题、理解 _adapt_sql 占位符转换机制时使用。
  触发词：ICPC、竞赛数据库、icpc_db、icpc_database、get_icpc_db_connection、
  _adapt_sql、IcpcSession、icpc_db_pool、IcpcBase、check_up、duel、
  sub_records、real_time_problems、shadow_problem_view、%s、CTE、
  ROW_NUMBER、JSON_SEARCH。
---

# ICPC DB 数据库操作指南

> 针对 ICPC（竞赛）数据库的原始 SQL 异步查询规范。
>
> **与 Bot DB 的核心差异**：ICPC DB 不使用 ORM 查询、没有 CRUD 包装函数。
> 所有操作通过 `get_icpc_db_connection()` -> `IcpcSession.execute()` 执行原始 SQL。
> 查询使用 `%s` 占位符（自动适配为 `:N`），返回 `list[dict]`。

## 架构概览

```
环境变量 (.env / .env.{ENVIRONMENT})
  └─ ICPC_DB_HOST, ICPC_DB_USER, ICPC_DB_PASSWORD,
     ICPC_DB_NAME, ICPC_DB_PORT, ICPC_DB_POOL_SIZE
       │
       ▼
src/common/icpc_database.py
  ├─ icpc_engine          = create_async_engine("mysql+asyncmy://...")
  ├─ icpc_async_session_factory = async_sessionmaker(engine, expire_on_commit=False)
  └─ IcpcBase             = DeclarativeBase  ← 所有 ICPC 模型继承它（仅供文档参考）
       │
       ▼
src/common/icpc_db_pool.py          ← **实际使用的查询层**
  ├─ IcpcSession                   包装器：execute() 返回 list[dict]
  ├─     _adapt_sql()              %s → :1, :2, :3 自动转换
  ├─ get_icpc_db_connection()      异步上下文管理器入口
  └─ close_icpc_engine()           优雅关闭时释放引擎
       │
       ▼
src/common/models/icpc_models.py   ← **ORM 模型仅供文档参考，查询不使用它们**
  ├─ DingCheckup
  ├─ CfOfficialProblem
  ├─ IcpcUser (+ OjAccount)
  ├─ CfAllSubmission
  └─ LuoguAllSubmission
       │
       ▼
data/sql/read/*.sql                 ← 5 个 SQL 文件，使用 %s 占位符
```

| 组件 | 说明 |
|---|---|
| 驱动 | `asyncmy`（异步 MySQL） — 与 Bot DB 相同的异步驱动 |
| 连接池 | `pool_pre_ping=True`, `pool_recycle=3600`, 池大小由 `ICPC_DB_POOL_SIZE` 控制（默认 20） |
| 最大溢出 | `max_overflow=10` |
| 会话 | `expire_on_commit=False` |
| 基类 | `IcpcBase = DeclarativeBase`（独立于 Bot DB 的 `Base`） |
| **查询方式** | **原始 SQL**（`text()` 包装），不使用 ORM |
| **返回类型** | **`list[dict]`**（每行一个字典），不等同于 ORM 模型实例 |

**环境配置**：6 个 `ICPC_DB_*` 环境变量在 `src/config/local_config.py` 的 `IcpcDBConfig` 中定义：

| 环境变量 | 默认值 | 说明 |
|---|---|---|
| `ICPC_DB_HOST` | `localhost` | ICPC 数据库主机 |
| `ICPC_DB_USER` | `root` | ICPC 数据库用户名 |
| `ICPC_DB_PASSWORD` | `''` | ICPC 数据库密码 |
| `ICPC_DB_NAME` | `''` | ICPC 数据库名 |
| `ICPC_DB_PORT` | `3306` | ICPC 数据库端口 |
| `ICPC_DB_POOL_SIZE` | `20` | 连接池大小 |

---

## 1. 获取连接

所有 ICPC 数据库操作的入口是 `get_icpc_db_connection()` 上下文管理器：

```python
from src.common import get_icpc_db_connection

async def example():
    async with get_icpc_db_connection() as db:
        rows = await db.execute("SELECT * FROM user WHERE id = %s", [42])
        for row in rows:
            print(row["real_name"], row["school"])
```

`db` 是 `IcpcSession` 实例，它包装了 SQLAlchemy 的 `AsyncSession`，提供与旧版 `mysql-connector-python` 兼容的接口。

### 1.1 导入方式

推荐从 `src.common` 导入（该模块已 re-export）：

```python
from src.common import get_icpc_db_connection
# 或者从具体模块导入
from src.common.icpc_db_pool import get_icpc_db_connection
```

### 1.2 绝对不要在模块顶层获取连接

```python
# ❌ 错误：插件 import 时就打开数据库连接
async with get_icpc_db_connection() as db:  # 报错！
    ...

# ✅ 正确：放在 async 函数/命令处理器内部
@cmd.handle()
async def handler():
    async with get_icpc_db_connection() as db:
        ...
```

### 1.3 关闭引擎

应用关闭时释放 ICPC 引擎资源：

```python
from src.common.icpc_db_pool import close_icpc_engine

# 在应用关闭时调用
await close_icpc_engine()
```

---

## 2. 执行查询

### 2.1 基本查询 — `db.execute()`

```python
async with get_icpc_db_connection() as db:
    # 无参数查询
    rows = await db.execute("SELECT * FROM user")
    # rows → [{"id": 1, "real_name": "张三", ...}, {"id": 2, ...}]

    # 带参数的查询 — 使用 %s 占位符
    rows = await db.execute(
        "SELECT * FROM user WHERE id = %s AND school = %s",
        [42, "HIT"]
    )

    # 也可以传元组
    rows = await db.execute(
        "SELECT name, time FROM ding_checkup WHERE time >= %s AND time <= %s",
        (start_time, end_time)
    )
```

### 2.2 返回类型

`execute()` 总是返回 **`list[dict]`**，与旧版 `fetchall()` 行为一致：

```python
rows = await db.execute("SELECT id, real_name FROM user")
# rows = [
#     {"id": 1, "real_name": "张三"},
#     {"id": 2, "real_name": "李四"},
# ]

# 通过字典键访问
for row in rows:
    print(row["id"], row["real_name"])
```

- 没有结果时返回空列表 `[]`，不会返回 `None`
- 每一行是一个普通 Python `dict`

### 2.3 批量操作 — `db.execute_many()`

```python
async with get_icpc_db_connection() as db:
    await db.execute_many(
        "INSERT INTO your_table (col1, col2) VALUES (%s, %s)",
        [
            [val1, val2],
            [val3, val4],
        ]
    )
    # 自动 commit
```

`execute_many()` 在全部执行结束后自动 `commit`，无需手动提交。

### 2.4 错误处理模式

所有 5 个消费者插件都使用统一的错误处理模式：

```python
async with get_icpc_db_connection() as db:
    try:
        records = await db.execute(query, params)
        return records
    except Exception:
        logger.error(f"ICPC DB 查询失败：{query[:200]}...")
        return []  # 一律返回空列表
```

---

## 3. `_adapt_sql()` 机制详解

这是 ICPC DB 兼容层的核心机制。`IcpcSession._adapt_sql()` 将 MySQL 风格的 `%s` 占位符自动转换为 SQLAlchemy `text()` 所需的 `:N` 数字占位符。

### 3.1 为什么需要这个转换

- 原始 SQL 文件使用 **`%s`** 占位符（MySQL Connector / Python 风格）
- 但 SQLAlchemy 的 `text()` 要求使用 **`:name`** 或 **`:N`** 风格的命名占位符
- `_adapt_sql()` 作为桥梁，自动完成转换，让旧 SQL 文件无需修改即可在新架构下运行

### 3.2 转换规则

```
原始  →  "WHERE id = %s AND name = %s"
转换  →  "WHERE id = :1 AND name = :2"
```

```python
# 实际实现（简化版）
@staticmethod
def _adapt_sql(sql: str) -> str:
    counter = [0]

    def _replacer(_match):
        counter[0] += 1
        return f":{counter[0]}"

    return re.sub(r"%s", _replacer, sql)
```

### 3.3 参数绑定过程

转换后的 SQL 被 `text()` 包装，同时构造参数字典：

```python
# 如果 params = [start_time, end_time]
# SQL 被转换为: "WHERE time >= :1 AND time <= :2"
# 参数字典: {":1": start_time, ":2": end_time}  → 实际是 {"1": start_time, "2": end_time}

param_dict = {}
for i, val in enumerate(params, 1):
    param_dict[str(i)] = val

result = await self._session.execute(text(adapted_sql), param_dict)
```

### 3.4 重要限制

- **不支持混合风格**：不要在同一 SQL 中同时使用 `%s` 和手工 `:N`
- **%s 顺序必须和参数列表顺序一致**：`_adapt_sql()` 是顺序计数的，第 N 个 `%s` 对应参数列表的第 N 个元素
- **%s 不会被转义**：如果你的数据中恰好包含 `%s` 字面量，会被错误转换。但实际查询中不可能出现这种情况

---

## 4. 加载 SQL 文件

所有 ICPC DB 查询都从 `.sql` 文件中读取，而不是在 Python 代码中硬编码 SQL 字符串。

### 4.1 `GetSQL.read_sql_file()`

```python
from src.common.utils import GetSQL

# 使用 read/ 下的文件
query = GetSQL.read_sql_file("read/get_ding_range_checkup.sql")
```

### 4.2 文件位置和配置

SQL 文件存放在 `data/sql/read/` 目录下。`GetSQL.read_sql_file()` 内部会拼接 `DiTingData.SQL_DIR` 基路径，因此插件 config 只需存储相对路径：

```python
# src/plugins/check_up/config.py
class Config(BaseModel):
    GET_DING_RANGE_CHECKUP: str = "read/get_ding_range_checkup.sql"
```

然后在插件中：

```python
from src.common.utils import GetSQL
from .config import config

query = GetSQL.read_sql_file(config.GET_DING_RANGE_CHECKUP)
# GetSQL 内部拼接: DiTingData.SQL_DIR + "read/get_ding_range_checkup.sql"
# → 例如 "/app/data/sql/read/get_ding_range_checkup.sql"
```

### 4.3 `DiTingData.SQL_DIR`

SQL 目录的基路径由 `DiTingData` 配置控制（环境变量 `SQL_DIR`），默认为 `/app/data/sql`。当你调用 `GetSQL.read_sql_file(relative_path)` 时，路径拼接由 `GetSQL` 内部完成——**不要在 config 中拼接 `SQL_DIR`**。

---

## 5. SQL 文件一览

ICPC DB 共有 **5 个活跃的 SQL 文件**，覆盖了从简单到极其复杂的查询模式。

### 5.1 `get_ding_range_checkup.sql` — 简单二参数查询

**路径**：`data/sql/read/get_ding_range_checkup.sql`

**SQL**：
```sql
SELECT name, time, check_type
FROM ding_checkup
WHERE time >= %s AND time <= %s
ORDER BY name ASC, time ASC
```

**参数**：2 个（start_time, end_time）

**使用者**：`check_up` 插件

**模式**：最简单的 SELECT + 时间范围过滤，无 JOIN、无聚合、无 CTE。

### 5.2 `get_cf_official_problems.sql` — 动态 SQL（0 基础参数 + 运行时拼接）

**路径**：`data/sql/read/get_cf_official_problems.sql`

**SQL**：
```sql
SELECT problem_id
FROM cf_official_problems
WHERE 1 = 1
```

**参数**：0 个基础参数，运行时动态追加

**使用者**：`duel` 插件

**模式**：文件本身只提供基础框架，插件在运行时**动态拼接**额外的 WHERE 条件：

```python
query = GetSQL.read_sql_file(config.GET_CF_OFFICIAL_PROBLEMS)
params = []

if rating is not None:
    query += "AND rating = %s\n"
    params.append(rating)

if tags:
    tag_patterns = ['%' + tag.lower() + '%' for tag in tags]
    tag_conditions = " AND ".join([
        "JSON_SEARCH(LOWER(tags), 'all', %s) IS NOT NULL"
    ] * len(tags))
    query += f"AND {tag_conditions}\n"
    params.extend(tag_patterns)

records = await db.execute(query, params)
```

**关键技巧**：
- 使用 `WHERE 1 = 1` 技巧方便动态拼接 `AND` 子句
- 使用 **`JSON_SEARCH(LOWER(tags), 'all', %s)`** 在 MySQL JSON 数组中做不区分大小写的模糊搜索
- 每个 tag 生成一个 `JSON_SEARCH(...) IS NOT NULL` 条件，各条件之间用 `AND` 连接

### 5.3 `sub_records_get_range_records.sql` — CTE + UNION ALL + 聚合

**路径**：`data/sql/read/sub_records_get_range_records.sql`

**参数**：4 个（start, end, start, end — 两个平台各用一组时间范围）

**使用者**：`sub_records` 插件

**SQL 模式**：CTE + UNION ALL + 聚合

```sql
WITH sub_data AS (
    -- 洛谷提交统计
    SELECT u.real_name, u.school, u.role_id,
           0 AS cf_count,
           COUNT(DISTINCT l.problem_id) AS luogu_count,
           COUNT(DISTINCT l.problem_id) AS all_count
    FROM user u
        JOIN oj_account oa ON u.id = oa.user_id
        JOIN luogu_all_submissions AS l ON l.uid = oa.luogu_uid AND l.is_pass = 1
            AND l.creation_time BETWEEN %s AND %s
    GROUP BY u.real_name, u.school, u.role_id

    UNION ALL

    -- Codeforces 提交统计
    SELECT u.real_name, u.school, u.role_id,
           COUNT(DISTINCT c.problem_id) AS cf_count,
           0 AS luogu_count,
           COUNT(DISTINCT c.problem_id) AS all_count
    FROM user u
        JOIN oj_account oa ON u.id = oa.user_id
        JOIN cf_all_submissions AS c ON c.account = oa.cf_account AND c.verdict = 'OK'
            AND c.creation_time BETWEEN %s AND %s
    GROUP BY u.real_name, u.school, u.role_id
)
SELECT real_name, SUM(cf_count), SUM(luogu_count), SUM(all_count), school, role_id
FROM sub_data
GROUP BY real_name, school, role_id
ORDER BY all_count DESC;
```

**参数传递代码**：
```python
# sub_records: 4 参数，start_time 和 end_time 各重复两次
records = await db.execute(query, (start_time, end_time, start_time, end_time))
```

### 5.4 `get_hour_sub_records.sql` — 双 CTE + ROW_NUMBER 窗口函数

**路径**：`data/sql/read/get_hour_sub_records.sql`

**参数**：4 个（start, end, start, end — 两个平台各用一组时间范围）

**使用者**：`real_time_problems` 插件

**SQL 模式**：两层 CTE + ROW_NUMBER() 窗口函数去重

```sql
WITH ranked_data AS (
    -- CF 部分
    SELECT u.real_name, 'CF' AS platform, c.problem_id, c.problem_name,
           c.rating AS difficulty, c.creation_time AS ac_time, u.enter_time
    FROM user u
        LEFT JOIN oj_account a ON a.user_id = u.id
        LEFT JOIN cf_all_submissions c ON c.account = a.cf_account AND c.verdict = 'OK'
            AND c.creation_time BETWEEN %s AND %s
    WHERE c.sub_id IS NOT NULL

    UNION ALL

    -- 洛谷部分
    SELECT u.real_name, '洛谷', l.problem_id, l.problem_name,
           l.difficulty, l.creation_time, u.enter_time
    FROM user u
        LEFT JOIN oj_account a ON a.user_id = u.id
        LEFT JOIN luogu_all_submissions l ON l.uid = a.luogu_uid AND l.is_pass = 1
            AND l.creation_time BETWEEN %s AND %s
    WHERE l.is_pass IS NOT NULL
),
numbered AS (
    SELECT *,
           ROW_NUMBER() OVER (
               PARTITION BY real_name, platform, problem_id, DATE(ac_time)
               ORDER BY ac_time ASC
           ) AS rn
    FROM ranked_data
)
SELECT realName, platform, problemId, problemName, difficulty, acTime, enterTime
FROM numbered
WHERE rn = 1
ORDER BY realName, acTime;
```

**参数传递代码**：
```python
# real_time_problems: 使用列表乘法构造 4 参数
records = await db.execute(query, ([start_time, end_time] * 2))
# 等价于 [start_time, end_time, start_time, end_time]
```

**去重逻辑**：`ROW_NUMBER() OVER (PARTITION BY real_name, platform, problem_id, DATE(ac_time))` 为同一个用户、同一平台、同一题目、同一天内的多条提交生成序号，`WHERE rn = 1` 只保留最早的 AC 记录。

### 5.5 `get_daily_sub_records.sql` — 多年度数据库扫描（16 参数）

**路径**：`data/sql/read/get_daily_sub_records.sql`

**参数**：**16 个**（4 个年份 × 2 个平台 × 2 个边界 = 16 个 `%s`）

**使用者**：`shadow_problem_view` 插件

**SQL 模式**：两层 CTE + ROW_NUMBER() + **多年度 OR 条件**

```sql
WITH ranked_data AS (
    -- CF 部分，跨 4 个年度范围
    SELECT u.real_name, 'CF' AS platform, ...
    FROM user u
        LEFT JOIN oj_account a ON a.user_id = u.id
        LEFT JOIN cf_all_submissions c ON c.account = a.cf_account AND c.verdict = 'OK'
        AND (
            c.creation_time BETWEEN %s AND %s OR   -- 年份 1
            c.creation_time BETWEEN %s AND %s OR   -- 年份 2
            c.creation_time BETWEEN %s AND %s OR   -- 年份 3
            c.creation_time BETWEEN %s AND %s      -- 年份 4
        )
    WHERE c.sub_id IS NOT NULL

    UNION ALL

    -- 洛谷部分，同样跨 4 个年度范围
    SELECT u.real_name, '洛谷', ...
    FROM user u
        LEFT JOIN oj_account a ON a.user_id = u.id
        LEFT JOIN luogu_all_submissions l ON l.uid = a.luogu_uid AND l.is_pass = 1
        AND (
            l.creation_time BETWEEN %s AND %s OR   -- 年份 1
            l.creation_time BETWEEN %s AND %s OR   -- 年份 2
            l.creation_time BETWEEN %s AND %s OR   -- 年份 3
            l.creation_time BETWEEN %s AND %s      -- 年份 4
        )
    WHERE l.is_pass IS NOT NULL
),
numbered AS (
    SELECT *, ROW_NUMBER() OVER (PARTITION BY ... ORDER BY ac_time ASC) AS rn
    FROM ranked_data
)
SELECT ... FROM numbered WHERE rn = 1 ORDER BY ...;
```

**参数传递代码**：
```python
# shadow_problem_view: 16 参数，4 年 × 2 平台 × 2 边界
time_ranges = []
cur_year = start_datetime.year
for year_offset in range(4):
    year = cur_year - year_offset
    past_start = start_datetime.replace(year=year)
    past_end = end_datetime.replace(year=year)
    time_ranges.extend([past_start, past_end])

# time_ranges 现在包含 8 个值（4 年 × 2 边界）
# time_ranges * 2 复制为 16 个值（CF 部分 + 洛谷部分）
records = await db.execute(query, (time_ranges * 2))
```

---

## 6. 参数传递模式总结

ICPC DB 的参数传递有多种风格，理解每个模式很重要：

| 模式 | 语法 | 示例 | 使用者 |
|---|---|---|---|
| 元组传递 | `(a, b)` | `(start_time, end_time)` | check_up, sub_records |
| 列表传递 | `[a, b]` | `[rating] + tag_patterns` | duel |
| 列表乘法 | `[a, b] * N` | `[start, end] * 2` | real_time_problems |
| 元组乘法 | `(list * N)` | `(time_ranges * 2)` | shadow_problem_view |
| 无参数 | — | `execute(query)` (params=None) | duel (获取全部题目) |

**所有 5 个插件都遵循同一个模式**：通过 `async with get_icpc_db_connection() as db:` 获取连接，调用 `await db.execute(query, params)`，在 `try/except` 中处理异常，失败时返回 `[]`。

---

## 7. ORM 模型（仅供参考）

`src/common/models/icpc_models.py` 定义了 6 个 ORM 模型，均继承 `IcpcBase`。

> **重要**：这些模型**仅用于文档参考和代码补全**。实际查询不使用 ORM，而是直接使用原始 SQL。列类型和约束仅供参考——它们只覆盖了插件查询中用到的列，不保证与 MySQL 表结构完全匹配。

### 7.1 模型一览

| # | 模型类 | MySQL 表名 | 用途 | 主键 |
|---|--------|-----------|------|------|
| 1 | `DingCheckup` | `ding_checkup` | 考勤打卡记录 | `(name, time)` 复合主键 |
| 2 | `CfOfficialProblem` | `cf_official_problems` | Codeforces 官方题库 | `problem_id` |
| 3 | `IcpcUser` | `user` | 用户/队员信息 | `id` |
| 4 | `OjAccount` | `oj_account` | OJ 账号映射 | `user_id` |
| 5 | `CfAllSubmission` | `cf_all_submissions` | Codeforces 全部提交记录 | `sub_id` |
| 6 | `LuoguAllSubmission` | `luogu_all_submissions` | 洛谷全部提交记录 | `sub_id` |

### 7.2 模型详情

#### DingCheckup — 考勤打卡记录

| 列 | 类型 | 约束 |
|---|---|---|
| `name` | `String(128)` | PK |
| `time` | `DateTime` | PK |
| `check_type` | `String(32)` | |

#### CfOfficialProblem — Codeforces 官方题库

| 列 | 类型 | 约束 |
|---|---|---|
| `problem_id` | `String(64)` | PK |
| `rating` | `Integer` | nullable |
| `tags` | `JSON` | nullable — MySQL JSON 数组，如 `["dp", "math"]` |

**查询注意**：`tags` 是 JSON 类型，查询时用 `JSON_SEARCH(LOWER(tags), 'all', %s)` 做不区分大小写搜索。

#### IcpcUser — 用户/队员信息

| 列 | 类型 | 约束 |
|---|---|---|
| `id` | `Integer` | PK |
| `real_name` | `String(128)` | nullable |
| `school` | `String(128)` | nullable |
| `role_id` | `Integer` | nullable |
| `enter_time` | `Date` | nullable |

**查询注意**：与 `oj_account` 通过 `user.id = oj_account.user_id` 关联。

#### OjAccount — OJ 账号映射

| 列 | 类型 | 约束 |
|---|---|---|
| `user_id` | `Integer` | PK，→ `user.id` |
| `cf_account` | `String(128)` | nullable — Codeforces 用户名 |
| `luogu_uid` | `String(64)` | nullable — 洛谷 UID（字符串！） |

#### CfAllSubmission — Codeforces 全部提交记录

| 列 | 类型 | 约束 |
|---|---|---|
| `sub_id` | `BigInteger` | PK |
| `account` | `String(128)` | nullable → `oj_account.cf_account` |
| `problem_id` | `String(64)` | nullable |
| `problem_name` | `String(256)` | nullable |
| `rating` | `Integer` | nullable |
| `creation_time` | `DateTime` | nullable |
| `verdict` | `String(64)` | nullable — 值为 `'OK'` 表示通过 |

**查询注意**：AC 提交筛选条件为 `verdict = 'OK'`。

#### LuoguAllSubmission — 洛谷全部提交记录

| 列 | 类型 | 约束 |
|---|---|---|
| `sub_id` | `BigInteger` | PK |
| `uid` | `String(64)` | nullable → `oj_account.luogu_uid`（注意是字符串！） |
| `problem_id` | `String(64)` | nullable |
| `problem_name` | `String(256)` | nullable |
| `difficulty` | `Integer` | nullable |
| `creation_time` | `DateTime` | nullable |
| `is_pass` | `Integer` | nullable — 值为 1 表示通过 |

**查询注意**：
- AC 提交筛选条件为 `is_pass = 1`
- `luogu_uid` 在 `OjAccount` 中定义为 `String`，JOIN 时注意类型一致

### 7.3 导入方式

```python
# 这些导入仅供类型提示和代码参考，不是执行查询所必需的
from src.common.models.icpc_models import DingCheckup, CfOfficialProblem
from src.common.models.icpc_models import IcpcUser, OjAccount
from src.common.models.icpc_models import CfAllSubmission, LuoguAllSubmission
```

---

## 8. 插件实战参考

以下是项目中每个使用 ICPC DB 的插件及其查询模式，可作为写新代码时的参考：

| 插件 | SQL 文件 | 参数数 | 查询特点 | 结果处理 |
|---|---|---|---|---|
| `check_up` | `get_ding_range_checkup.sql` | 2 | 最简单的 WHERE 时间范围 | `record["name"]`, `record["time"]`, `record["check_type"]` 计算出勤 |
| `duel` | `get_cf_official_problems.sql` | 0-N | **动态拼接** SQL + `JSON_SEARCH` 标签搜索 | `random.choice(rows)["problem_id"]` |
| `sub_records` | `sub_records_get_range_records.sql` | 4 | CTE + UNION ALL + 聚合 | `record["real_name"]`, `record["cf_count"]`, `record["luogu_count"]` 构建排名消息和 HTML 表格 |
| `real_time_problems` | `get_hour_sub_records.sql` | 4 | 2 层 CTE + ROW_NUMBER 去重 | 外部调用者进一步处理 |
| `shadow_problem_view` | `get_daily_sub_records.sql` | **16** | 多年度范围 + CTE + ROW_NUMBER | 外部调用者进一步处理 |

### 8.1 check_up — 简单考勤查询

**文件**：`src/plugins/check_up/working_time.py`

```python
from ...common import get_icpc_db_connection, utils

async def _get_range_records(range_start, range_end):
    query = utils.GetSQL.read_sql_file(config.GET_DING_RANGE_CHECKUP)
    try:
        async with get_icpc_db_connection() as db:
            records = await db.execute(query, (range_start, range_end))
            return records
    except Exception:
        return []

# 结果处理
def _calculate_attendance(records):
    for record in records:
        name = record["name"]
        time = record["time"]
        check_type = record["check_type"]
        # ... 计算出勤
```

### 8.2 duel — 动态 SQL + JSON 标签搜索

**文件**：`src/plugins/duel/get_problem.py`

```python
from ...common import get_icpc_db_connection

# 获取全部题目
async def _get_all_problem_id():
    query = GetSQL.read_sql_file(config.GET_CF_OFFICIAL_PROBLEMS)
    async with get_icpc_db_connection() as db:
        records = await db.execute(query=query)
        return [r["problem_id"] for r in records]

# 按 rating + tags 筛选（动态 SQL！）
async def _match_id_by_rating_tags(rating, tags):
    query = GetSQL.read_sql_file(config.GET_CF_OFFICIAL_PROBLEMS)
    params = []

    if rating is not None:
        query += "AND rating = %s\n"
        params.append(rating)

    if tags:
        tag_patterns = ['%' + t.lower() + '%' for t in tags]
        tag_conditions = " AND ".join([
            "JSON_SEARCH(LOWER(tags), 'all', %s) IS NOT NULL"
        ] * len(tags))
        query += f"AND {tag_conditions}\n"
        params.extend(tag_patterns)

    async with get_icpc_db_connection() as db:
        records = await db.execute(query, params)
        return [r["problem_id"] for r in records]
```

### 8.3 sub_records — CTE + 跨平台提交统计

**文件**：`src/plugins/sub_records/sub_condition.py`

```python
@staticmethod
async def _get_range_sub_records(start_time, end_time):
    query = utils.GetSQL.read_sql_file(config.GET_RANGE_SUB_RECORDS)
    try:
        async with get_icpc_db_connection() as db:
            records = await db.execute(query, (start_time, end_time, start_time, end_time))
            return records
    except Exception:
        return []

# 结果处理：构建文本消息和排名表格
def get_records_msg(records):
    for record in records:
        # record["real_name"], record["cf_count"], record["luogu_count"], record["school"]
        ...

def create_ranking_table(records):
    for record in records:
        # record["real_name"], record["school"], record["role_id"]
        # record["cf_count"], record["luogu_count"], record["all_count"]
        ...
```

### 8.4 real_time_problems — ROW_NUMBER 去重

**文件**：`src/plugins/real_time_problems/get_hour_problems.py`

```python
@classmethod
async def get_hour_sub_records(cls, start_time, end_time):
    query = utils.GetSQL.read_sql_file(config.GET_HOUR_SUB_RECORDS)
    try:
        async with get_icpc_db_connection() as db:
            records = await db.execute(query, ([start_time, end_time] * 2))
            return records
    except Exception:
        return []
```

### 8.5 shadow_problem_view — 多年度遍历 + 16 参数

**文件**：`src/plugins/shadow_problem_view/get_range_sub.py`

```python
@classmethod
async def get_daily_sub_records(cls, start_datetime, end_datetime):
    # 构造 4 年时间范围
    time_ranges = []
    cur_year = start_datetime.year
    for year_offset in range(4):
        year = cur_year - year_offset
        past_start = start_datetime.replace(year=year)
        past_end = end_datetime.replace(year=year)
        time_ranges.extend([past_start, past_end])

    query = utils.GetSQL.read_sql_file(config.GET_DAILY_SUB_RECORDS)
    try:
        async with get_icpc_db_connection() as db:
            # time_ranges 有 8 个值，*2 后为 16 个值
            records = await db.execute(query, (time_ranges * 2))
            return records
    except Exception:
        return []
```

---

## 9. 常见陷阱

### 9.1 参数数量不匹配

```python
# ❌ 错误：SQL 中有 4 个 %s，但只传了 2 个参数
query = "WHERE ... BETWEEN %s AND %s AND ... BETWEEN %s AND %s"
await db.execute(query, (start, end))

# ✅ 正确：参数数量必须与 %s 完全匹配
await db.execute(query, (start, end, start, end))
```

特别是 `sub_records_get_range_records.sql` 和 `get_hour_sub_records.sql` 都有 4 个 `%s`，必须传 4 个参数——各平台的时间区间需要重复传入。

### 9.2 16 参数陷阱（shadow_problem_view）

这是最容易出错的地方。`get_daily_sub_records.sql` 有 **16 个** `%s` 占位符：

- CF 部分：4 个年份 × 2 个边界 = 8 个 `%s`
- 洛谷部分：4 个年份 × 2 个边界 = 8 个 `%s`
- 总计：**16 个** `%s`

```python
# ✅ 正确：构造 4 年时间范围后复制两份
time_ranges = []
for year_offset in range(4):
    ...
    time_ranges.extend([past_start, past_end])
# time_ranges = [s1, e1, s2, e2, s3, e3, s4, e4]  ← 8 个值
records = await db.execute(query, (time_ranges * 2))  # ← 16 个值

# ❌ 错误：只传了 2 个参数
records = await db.execute(query, (start, end))
```

### 9.3 duel 动态 SQL 的 `%s` 计数

`duel` 插件在运行时动态拼接 SQL，因此 `%s` 数量不固定：

```python
# 假设 rating=1500, tags=["dp", "math"]
# 拼接后的 SQL 有 3 个 %s
query = "SELECT ... WHERE 1 = 1\n"
query += "AND rating = %s\n"           # → 1 个 %s
query += "AND JSON_SEARCH(..., %s) IS NOT NULL\n"  # → dp：1 个 %s
query += "AND JSON_SEARCH(..., %s) IS NOT NULL\n"  # → math：1 个 %s
# 总共 3 个 %s，params = [1500, "%dp%", "%math%"]

# 务必保证 params 长度与 %s 数量一致
```

### 9.4 datetime 处理 — 全部使用 naive 北京时间

ICPC DB 的 DateTime 列同样使用 **naive datetime**（无时区信息），时区约定为北京时间（Asia/Shanghai）：

```python
from datetime import datetime

# ✅ 正确：使用 naive datetime
now = datetime.now()

# 构造时间范围
start_time = datetime(2026, 7, 1, 4, 0, 0)
end_time = datetime(2026, 7, 2, 4, 0, 0)
```

如果外部数据源传入带时区的 datetime，需要剥离 tzinfo：

```python
def _ensure_naive_local(dt):
    if dt is None:
        return None
    if dt.tzinfo is not None and dt.tzinfo.utcoffset(dt) is not None:
        return dt.replace(tzinfo=None)
    return dt
```

### 9.5 不要使用 ORM 模型进行查询

```python
# ❌ 错误：ICPC DB 不使用 ORM 查询
from src.common.models.icpc_models import DingCheckup

async with icpc_async_session_factory() as session:
    result = await session.execute(select(DingCheckup).where(...))
    # 虽然技术上可行，但这不是 ICPC DB 的设计模式

# ✅ 正确：使用原始 SQL + get_icpc_db_connection()
from src.common import get_icpc_db_connection

async with get_icpc_db_connection() as db:
    rows = await db.execute(
        "SELECT name, time FROM ding_checkup WHERE time >= %s",
        [start_time]
    )
```

> **例外**：`icpc_async_session_factory` 可以直接使用 SQLAlchemy 查询，但当前所有消费者插件都使用 `get_icpc_db_connection()`。如果你需要使用 ORM 查询（例如复杂的关系加载），可以使用 `icpc_async_session_factory` 配合 `text()`，但确保团队理解这个异类。

### 9.6 不要在模块顶层调用 `get_icpc_db_connection()`

```python
# ❌ 错误：模块导入时打开连接
async with get_icpc_db_connection() as db:  # RuntimeError！
    ...

# ✅ 正确：在异步函数/命令处理器内部使用
@cmd.handle()
async def handler():
    async with get_icpc_db_connection() as db:
        ...

# ✅ 正确：在 @classmethod 中使用
@classmethod
async def query_method(cls):
    async with get_icpc_db_connection() as db:
        ...
```

### 9.7 `%s` 与 `:N` 不要混用

```python
# ❌ 错误：不能混用 %s 和手工 :N
query = "WHERE id = %s AND name = :1"  # _adapt_sql 会将其转为 ":1 AND name = :1"，产生不可预知的结果

# ✅ 正确：统一使用 %s
query = "WHERE id = %s AND name = %s"

# ✅ 正确：如果手工写 text()，统一使用 :N
query = "WHERE id = :1 AND name = :2"
```

### 9.8 `IcpcSession` 不是线程安全的

`IcpcSession` 包装的 SQLAlchemy `AsyncSession` 不是线程安全的。不要在不同协程间共享 `IcpcSession` 实例。始终在 `async with get_icpc_db_connection()` 块内使用。

### 9.9 不要混淆 `IcpcBase` 和 `Base`

```python
from src.common.database import Base              # ❌ Bot DB 的 Base
from src.common.icpc_database import IcpcBase     # ✅ ICPC DB 的 Base

# ICPC 模型必须继承 IcpcBase
class DingCheckup(IcpcBase):  # ✅ 正确
    ...

class DingCheckup(Base):      # ❌ 错误：会在 Bot DB 中建表
    ...
```

### 9.10 `execute_many` 自动 commit

`execute_many()` 在循环全部结束后自动 commit。不要在调用后重复 commit。如果要在同一个事务中混合执行 `execute()` 和 `execute_many()`，注意 `execute_many` 会 commit，后续的 `execute` 将在新事务中执行——此时应改用 `IcpcSession._session` 直接控制事务。

---

## 10. 与 Bot DB 的区别

这个项目有 **两套独立的数据库**，不要混淆：

| | Bot DB | ICPC DB |
|---|---|---|
| **环境变量前缀** | `BOT_DB_*` | `ICPC_DB_*` |
| **Session 工厂** | `src/common/database.py` → `async_session_factory` | `src/common/icpc_database.py` → `icpc_async_session_factory` |
| **Base 类** | `Base` | `IcpcBase` |
| **ORM 模型** | `src/common/models/botdb_models.py` + `like_plugin_models.py` | `src/common/models/icpc_models.py`（仅供文档参考） |
| **查询方式** | **ORM 查询**（`select()` + CRUD 包装器） | **原始 SQL**（`text()` + 自动 `%s` 适配） |
| **返回类型** | 模型实例 / `Row` | `list[dict]` |
| **CRUD 包装器** | `src/common/crud.py`（5 个函数） | **无** |
| **数据库名** | `diting_qq_bot` | 由 `ICPC_DB_NAME` 指定 |
| **本指南适用范围** | ❌ 不适用 — 参见下方引用 | ✅ 全部 |

对于 Bot DB 的操作（ORM 查询、CRUD 包装器、过滤器语法、关系加载等），请参见：

> **[DiTing Bot DB 操作指南](../../skills/diting-db-guide/SKILL.md)**

以下是一个并排对比，展示同样"查用户"的场景在两种数据库中的不同写法：

```python
# ─── Bot DB（ORM + CRUD）───
from src.common.crud import async_get_one
from src.common.models.botdb_models import Group

group = await async_get_one(Group, name="ACM")
# 返回模型实例，可以访问 group.id, group.display_name 等属性

# ─── ICPC DB（原始 SQL）───
from src.common import get_icpc_db_connection

async with get_icpc_db_connection() as db:
    rows = await db.execute(
        "SELECT id, real_name FROM user WHERE school = %s",
        ["HIT"]
    )
    # 返回 list[dict]，通过 rows[0]["id"] 访问
```

---

## 11. 添加新查询（快速参考）

如果需要为 ICPC DB 添加新的 SQL 查询，遵循以下步骤：

### 步骤

**（1）编写 SQL 文件** — 在 `data/sql/read/` 下创建 `.sql` 文件，使用 `%s` 占位符：

```sql
-- data/sql/read/get_my_new_query.sql
SELECT u.real_name, oa.cf_account
FROM user u
JOIN oj_account oa ON u.id = oa.user_id
WHERE oa.cf_account IS NOT NULL
  AND u.school = %s
ORDER BY u.real_name;
```

**（2）在插件 config.py 中注册路径**：

```python
# src/plugins/my_plugin/config.py
from pydantic import BaseModel

class Config(BaseModel):
    MY_NEW_QUERY: str = "read/get_my_new_query.sql"
```

**（3）在插件中使用**：

```python
from src.common import get_icpc_db_connection
from src.common.utils import GetSQL
from .config import Config

async def fetch_members(school: str):
    config = get_plugin_config(Config)
    query = GetSQL.read_sql_file(config.MY_NEW_QUERY)
    async with get_icpc_db_connection() as db:
        rows = await db.execute(query, [school])
        return rows
```

### 参数速查表

| 参数数 | 适合场景 | 示例 SQL 结构 |
|--------|---------|--------------|
| 0 | 全表遍历 | `SELECT * FROM table` |
| 1-2 | 简单过滤 | `WHERE col = %s` / `WHERE col BETWEEN %s AND %s` |
| 2N | 多平台对称查询 | `BETWEEN %s AND %s ... BETWEEN %s AND %s` |
| 4N | 多年度 × 多平台 | `BETWEEN %s AND %s OR ...`（每年两个参数） |
| 动态 | 条件可变 | `WHERE 1 = 1` + 运行时拼接 |

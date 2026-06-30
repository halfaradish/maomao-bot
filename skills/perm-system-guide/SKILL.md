---
name: perm-system-guide
description: >
  DiTing-NoneBot 权限系统集成与运维指南。
  当需要在插件中接入权限校验、注册新的权限点、通过管理面板配置黑白名单或权限组、
  排查权限拒绝问题、或理解 8 步优先级校验流程时使用。
  触发词：permission、权限、perm_key、check_permission、permission_checker、
  register_perm_point、PermissionChecker、perm_cache、TTLCache、
  白名单、黑名单、权限组、权限系统、permission_manager。
---

# DiTing 权限系统使用指南

> 完整的权限校验系统，提供 8 级优先级流程、三种接入方式、QQ 聊天管理面板。
> 基于 NoneBot Plugin + OneBot v11，单进程内存缓存。

## 架构概览

```
插件代码（三种接入方式）
  │
  ├─ A) Matcher 级:  permission_checker("plugin:action") | SUPERUSER
  │                    └─ on_command(..., permission=...) 直接传入
  │
  ├─ B) 命令式:      await check_permission(event, "plugin:action")
  │                    └─ 在任意 async 函数内直接调用，返回 bool
  │
  └─ C) 注册点:      register_perm_point("plugin:action", "名称", "描述", plugin_name="p")
                       └─ 插件 import 时调用，启动时自动同步到数据库
       │
       ▼
src/common/permission/
  ├─ __init__.py          ← 公共 API 出口（re-export 所有关键符号）
  ├─ registry.py          ← PermissionRegistry 内存单例 → PermissionPointDef
  ├─ checker.py           ← PermissionChecker 校验引擎（8 步判断 + 缓存）
  ├─ permission.py        ← permission_checker() → NoneBot Permission 适配器
  ├─ cache.py             ← TTLCache 内存缓存（默认 60 秒 TTL）
  ├─ supervisor.py        ← is_superuser() 读取 NoneBot SUPERUSERS
  ├─ models.py            ← 9 个 SQLAlchemy 模型（8 张表）
  └─ auto_register.py     ← 启动钩子：建表 + 同步权限点到数据库
       │
       ▼
src/plugins/permission_manager/  ← QQ 聊天管理面板
  ├─ __init__.py           ← 命令路由 + 所有管理操作实现
  ├─ permissions.py        ← 注册 permission_manager:manage 权限点
  └─ config.py             ← 配置：命令名、优先级、是否拦截
```

| 组件 | 说明 |
|---|---|
| 校验引擎 | `PermissionChecker.check()` — 8 步优先级流程，带 TTL 缓存 |
| 缓存 | `TTLCache` — 进程内内存缓存，默认 TTL 60 秒，管理操作时主动失效 |
| 注册表 | `PermissionRegistry` — 内存单例，插件 import 时收集权限点定义 |
| NoneBot 适配 | `permission_checker(perm_key)` → `Permission` 对象，可与 `SUPERUSER` 组合 |
| 启动同步 | `auto_register.py` 在 startup 时建表 + 将注册表同步到 `permission_points` 表 |
| 管理面板 | `permission_manager` 插件，通过 QQ 聊天命令管理全部权限配置 |

**核心约束**：
- 权限 key 格式：`plugin_name:action`（例如 `group_ban:ban`）
- 管理操作可由 **SUPERUSERS** 或拥有 `permission_manager:manage` 权限点的用户执行
- 缓存默认 60 秒过期，管理操作（增删改黑白名单/权限组/绑定）自动失效相关缓存
- 同步依赖 `async_session_factory`（Bot DB 的 SQLAlchemy session）

---

## 1. 声明权限点（注册）

所有受权限保护的功能必须先声明权限点。声明发生在 **插件 import 阶段**，由 `startup` 钩子自动同步到数据库。

### 1.1 注册 API

```python
from src.common.permission import register_perm_point

register_perm_point(
    "group_ban:ban",           # perm_key — 全局唯一，格式: plugin_name:action
    "禁言",                    # name — 功能名称（中文）
    "将指定成员禁言",          # description — 功能描述
    plugin_name="group_ban",   # 所属插件名（用于管理面板分组）
)
```

参数全部为字符串。`register_perm_point` 是 `PermissionRegistry.register` 的别名，**幂等**——重复注册同 key 不会报错，只有第一次生效。

### 1.2 标准声明模式

项目惯例是在插件目录下创建 `permissions.py` 集中声明，然后在 `__init__.py` 中导入触发注册：

```python
# src/plugins/group_ban/permissions.py
from src.common.permission import register_perm_point

register_perm_point("group_ban:ban", "禁言", "将指定成员禁言", plugin_name="group_ban")
register_perm_point("group_ban:unban", "解禁", "解除成员禁言", plugin_name="group_ban")
```

```python
# src/plugins/group_ban/__init__.py
from . import permissions  # noqa: F401 — 触发权限点注册
# ... 其余插件代码
```

### 1.3 启动时自动同步

`src/common/permission/auto_register.py` 在 NoneBot `on_startup` 阶段自动执行：

1. 调用 `Base.metadata.create_all` 建表（幂等，仅创建不存在的表）
2. 遍历 `perm_registry` 中所有已注册的权限点，逐个写入 `permission_points` 表

因此**不需要手动管理 DDL 或同步**，只需确保 `register_perm_point` 在插件 import 时被调用即可。

### 1.4 查看已注册的权限点

启动后在 QQ 中向机器人发送：

```
权限 注册点 列表
权限 注册点 列表 group_ban    # 按插件名筛选
```

---

## 2. 接入方式一：Matcher 级权限（推荐）

将权限检查直接绑定到 NoneBot 的 `on_command()` / `on_message()` 等 matcher 上。这是最简洁、最推荐的方式。

### 2.1 基本用法

```python
from nonebot import on_command
from nonebot.permission import SUPERUSER
from src.common.permission import permission_checker

ban_cmd = on_command(
    "ban",
    permission=permission_checker("group_ban:ban") | SUPERUSER,
)
```

`permission_checker("group_ban:ban")` 返回一个 `Permission` 对象。通过 `|`（逻辑或）与 `SUPERUSER` 组合后，**超级管理员或拥有 `group_ban:ban` 权限的用户**都能触发该命令。

### 2.2 组合多个权限

```python
from nonebot import on_command
from src.common.permission import permission_checker

# 管理员或群主都可操作
admin_cmd = on_command(
    "admin",
    permission=permission_checker("group_admin:ban")
              | permission_checker("group_admin:kick"),
)
```

### 2.3 完整插件示例

```python
# src/plugins/group_ban/__init__.py
from nonebot import on_command
from nonebot.adapters.onebot.v11 import Bot, GroupMessageEvent
from nonebot.params import CommandArg
from nonebot.permission import SUPERUSER

from . import permissions  # noqa: F401 — 先注册权限点
from src.common.permission import permission_checker

ban_cmd = on_command(
    "ban",
    permission=permission_checker("group_ban:ban") | SUPERUSER,
    priority=5,
    block=True,
)

@ban_cmd.handle()
async def handle_ban(bot: Bot, event: GroupMessageEvent, args: str = CommandArg()):
    user_id = args.extract_plain_text().strip()
    await bot.set_group_ban(
        group_id=event.group_id,
        user_id=int(user_id),
        duration=300,
    )
    await ban_cmd.finish(f"已将 {user_id} 禁言 5 分钟")
```

---

## 3. 接入方式二：命令式检查（Inline）

在函数体内部需要时才检查权限，适合非命令场景、条件分支、或对单个事件有多个权限检查需求。

### 3.1 基本用法

```python
from src.common.permission import check_permission

async def some_handler(event):
    if not await check_permission(event, "group_ban:ban"):
        await matcher.finish("你没有权限执行此操作")
    # 执行受保护的操作...
```

### 3.2 在事件处理器中使用

```python
@cmd.handle()
async def handler(event, matcher, args: str = CommandArg()):
    # 某个操作需要额外权限
    if args.extract_plain_text().strip() == "--all":
        if not await check_permission(event, "group_ban:batch_delete"):
            await matcher.finish("你没有批量删除的权限")
        # 执行批量删除...
```

### 3.3 方式选择建议

| 场景 | 使用方式 | 理由 |
|---|---|---|
| 命令整体需要权限 | Matcher 级（方式一） | 一行搞定，不符合直接不进入 handler |
| 同一命令中部分操作需要更高权限 | 命令式（方式二） | 在 handler 内部按条件检查 |
| 消息事件、定时任务等非命令场景 | 命令式（方式二） | Matcher 级只能用于 on_command/on_message |
| 需要自定义拒绝消息 | 命令式（方式二） | 可以自由给出具体提示 |
| 多个权限点组合（AND 关系） | 命令式（方式二） | 多个 `check_permission` 串联检查 |

---

## 4. 校验优先级（8 步流程）

`PermissionChecker._check_internal()` 按以下顺序逐级判断，**前面的规则优先于后面的规则**。

```
┌──────────────────────────────────────┐
│  0. 超级管理员（is_superuser）       │ → ✅ 直接放行（不缓存）
├──────────────────────────────────────┤
│  1. 用户黑名单（UserBlacklist）       │ → ❌ 拒绝
├──────────────────────────────────────┤
│  2. 群黑名单（GroupBlacklist）        │ → ❌ 拒绝
├──────────────────────────────────────┤
│  3. 群白名单（GroupWhitelist）        │ → ✅ 完全放行（跳过后续所有检查）
├──────────────────────────────────────┤
│  4. 用户白名单（UserWhitelist）       │ → ✅ 完全放行（跳过后续所有检查）
├──────────────────────────────────────┤
│  5. 权限组成员（PermissionGroupMember）│
│   + 匹配的 perm_key                   │ → ✅ 放行
│   所属的权限组拥有目标 perm_key       │
├──────────────────────────────────────┤
│  6. 群绑定（GroupPermBinding）         │
│   + 匹配的 perm_key                   │ → ✅ 放行
│   群绑定的权限组拥有目标 perm_key     │
├──────────────────────────────────────┤
│  7. 默认                             │ → ❌ 拒绝
└──────────────────────────────────────┘
```

### 关键细节

- **超级管理员绕过全部检查**：`is_superuser()` 返回 True 直接返回，且**不经过缓存**。
- **白名单是完全放行**：一旦命中群白名单或用户白名单，**不再检查 perm_key**——该用户/群的所有权限都被放行。
- **黑名单优先级高于白名单**：如果用户既在黑名单又在白名单，黑名单优先触发拒绝（步骤 1-2 在步骤 3-4 之前）。
- **权限组成员与群绑定是 OR 关系**：用户只要满足**任意一个**途径——直接是权限组成员 AND 该组拥有目标 perm_key → 通过；或所在群绑定了权限组 AND 该组拥有目标 perm_key → 通过。
- **必须同时匹配用户/群关系 AND perm_key**：用户属于某个权限组还不够——该权限组还必须**拥有被检查的 perm_key**。
- **默认拒绝**：不匹配任何规则的请求，最终返回 False。
- **整个流程使用同一个 session**：`_check_internal` 在单个 SQLAlchemy session 内完成全部查询，避免多次获取连接的开销。

---

## 5. 管理面板命令

`permission_manager` 插件通过 QQ 聊天提供管理界面，可执行权限由 `permission_manager:manage` 权限点控制——**超级管理员**默认拥有，也可通过权限组授予其他用户。

主命令：`权限`（别名 `perm`）

### 5.1 黑名单

```
权限 黑名单 添加 <QQ号> [原因]
权限 黑名单 移除 <QQ号>
权限 黑名单 列表
```

被加入黑名单的用户**所有权限均被拒绝**，且会跳过白名单检查（黑名单优先级高于白名单）。

### 5.2 白名单

用户白名单：

```
权限 白名单 用户 添加 <QQ号> [原因]
权限 白名单 用户 移除 <QQ号>
权限 白名单 用户 列表
```

群白名单：

```
权限 白名单 群 添加 <群号> [原因]
权限 白名单 群 移除 <群号>
权限 白名单 群 列表
```

白名单用户/群**完全放行所有权限**，不再检查权限组和 perm_key。

### 5.3 权限组

```
权限 权限组 创建 <名称> [展示名] [描述]
权限 权限组 删除 <名称>
权限 权限组 列表
权限 权限组 详情 <名称>
权限 权限组 添加成员 <名称> <QQ> [QQ...]
权限 权限组 移除成员 <名称> <QQ>
权限 权限组 添加权限 <名称> <perm_key> [perm_key...]
权限 权限组 移除权限 <名称> <perm_key>
权限 权限组 批量加群 <名称> <群号>
```

其中 `批量加群` 是快捷提示，实际将群内所有成员赋予权限组的功能需要通过下面 `绑定` 实现。

### 5.4 群绑定

```
权限 绑定 群 <群号> <权限组名>
权限 绑定 解除 <群号>
权限 绑定 列表 [群号]
```

群绑定是将一个 QQ 群**整体**与一个权限组关联。绑定后该群的**所有成员**都自动享有该权限组定义的全部权限（无需逐个添加成员）。底层在 checker 的步骤 6 中通过 `GroupPermBinding` 表查询实现。

### 5.5 注册点列表

```
权限 注册点 列表 [插件名]
```

显示所有已注册的权限点（按插件分组）。可以按插件名筛选。

### 5.6 查看用户状态

```
权限 查看 <QQ号>
```

一站式查看指定用户的权限状态：是否超级管理员、是否在黑名单/白名单、所属权限组及每个组拥有的权限点。

### 5.7 参数解析说明

命令参数支持 `@提及` 和纯文本两种形式。解析函数 `_tokenize_arguments()` 将消息段拆分为 `ArgToken` 列表：`at` 类型的 token 取其 `qq` 属性，`text` 类型的 token 按空格分词。

### 5.8 缓存失效策略

所有管理操作都会通过 `_invalidate_related_cache()` 失效相关缓存：

| 操作类型 | 失效策略 | 示例 |
|---|---|---|
| 用户黑名单添加/移除 | `clear_pattern("perm:{user_id}:")` | 失效该用户的所有缓存 |
| 群黑名单添加/移除 | `clear_pattern("perm::{group_id}:")` | 失效该群的所有缓存 |
| 用户白名单添加/移除 | `clear_pattern("perm:{user_id}:")` | 失效该用户的所有缓存 |
| 群白名单添加/移除 | `clear_pattern("perm::{group_id}:")` | 失效该群的所有缓存 |
| 权限组成员变更 | `clear_pattern("perm:{user_id}:")` | 失效该用户的所有缓存 |
| 权限组权限点变更 | `clear_all()` | 全局失效（影响范围不可预测） |
| 群绑定变更 | `clear_pattern("perm::{group_id}:")` | 失效该群的所有缓存 |

缓存键格式为 `perm:{user_id}:{group_id}:{perm_key}`。`clear_pattern` 做的是子字符串匹配（不是前缀匹配），所以 `perm:{user_id}:` 和 `perm::{group_id}:` 实际都通过包含匹配命中。

---

## 6. 模型一览

9 个 SQLAlchemy 模型（8 张表），全部继承 `src.common.database.Base`，定义在 `src/common/permission/models.py`。

### 6.1 表结构总览

| # | 模型类 | 表名 | 用途 | 关键约束 |
|---|--------|------|------|-----------|
| 1 | `PermissionPoint` | `permission_points` | 插件注册的权限点定义 | `perm_key` UNIQUE |
| 2 | `UserBlacklist` | `user_blacklist` | 用户黑名单 | `user_id` UNIQUE |
| 3 | `GroupBlacklist` | `group_blacklist` | 群黑名单 | `group_id` UNIQUE |
| 4 | `UserWhitelist` | `user_whitelist` | 用户白名单 | `user_id` UNIQUE |
| 5 | `GroupWhitelist` | `group_whitelist` | 群白名单 | `group_id` UNIQUE |
| 6 | `PermissionGroup` | `permission_groups` | 权限组/角色定义 | `name` UNIQUE; 关系 `members`, `permissions` |
| 7 | `PermissionGroupMember` | `permission_group_members` | 权限组成员 | 复合唯一 `(group_id, user_id)`; FK CASCADE |
| 8 | `PermissionGroupPerm` | `permission_group_perms` | 权限组拥有的权限点 | 复合唯一 `(group_id, perm_key)`; FK CASCADE |
| 9 | `GroupPermBinding` | `group_perm_bindings` | QQ 群与权限组绑定 | 复合唯一 `(qq_group_id, permission_group_id)`; FK CASCADE |

所有模型都有 `id`（BigInteger 自增主键）、`created_at`（DateTime, default=datetime.now）。`PermissionPoint` 和黑白名单模型有 `updated_at`（onupdate=datetime.now）。

### 6.2 关键关系

```
PermissionGroup 1 ── N PermissionGroupMember
     │                        │ (FK group_id, ON DELETE CASCADE)
     │                        └ user_id → QQ 号
     │
     ├── N PermissionGroupPerm
     │       │ (FK group_id, ON DELETE CASCADE)
     │       └ perm_key → 如 "group_ban:ban"
     │
     └── N GroupPermBinding
             │ (FK permission_group_id, ON DELETE CASCADE)
             └ qq_group_id → QQ 群号
```

- 删除 `PermissionGroup` 时，其 `members`、`permissions` 和所有 `GroupPermBinding` 全部级联删除
- SQLAlchemy 关系配置：`cascade="all, delete-orphan"` 确保 ORM 层的级联同步

### 6.3 导入方式

```python
# 校验相关（推荐从 __init__.py 导入）
from src.common.permission import (
    register_perm_point,     # 声明权限点
    check_permission,        # 命令式检查
    permission_checker,      # Matcher 级适配器
    is_superuser,            # 超级管理员判断
    perm_cache,              # 缓存操作
)

# 模型（从 models.py 导入，用于管理操作）
from src.common.permission.models import (
    PermissionPoint,
    UserBlacklist,
    GroupBlacklist,
    UserWhitelist,
    GroupWhitelist,
    PermissionGroup,
    PermissionGroupMember,
    PermissionGroupPerm,
    GroupPermBinding,
)
```

---

## 7. 缓存系统

### 7.1 工作原理

```python
from src.common.permission import perm_cache

# TTLCache 是简单的内存字典 + 过期时间
# 默认 TTL: 60 秒（在 cache.py 中硬编码）
# 键格式: "perm:{user_id}:{group_id}:{perm_key}"
# 值: True / False（校验结果）

# 查询缓存
cached = perm_cache.get("perm:123456:789012:group_ban:ban")
# → True / False / None（不存在或已过期）

# 手动设置缓存
perm_cache.set("perm:123456:789012:group_ban:ban", True, ttl=120)

# 按子串失效
perm_cache.clear_pattern("perm:123456:")   # 失效某个用户的所有缓存
perm_cache.clear_pattern("perm::789012:")   # 失效某个群的所有缓存

# 全局失效
perm_cache.clear_all()
```

### 7.2 何时需要手动操作缓存

一般不需要——校验引擎自动读写缓存，管理面板自动失效缓存。

但以下场景可能需要：

```python
from src.common.permission import perm_cache

# 场景：外部系统直接修改了数据库（绕过管理面板）
async def external_sync():
    # ... 直接修改了 UserBlacklist 表 ...
    await session.commit()
    perm_cache.clear_all()  # 确保下次校验获取最新结果
```

### 7.3 注意事项

- 缓存是进程内内存存储，**多进程部署不共享**——每个进程各自独立缓存
- 管理面板的 `_invalidate_related_cache()` 已覆盖所有内置修改场景，不需要额外处理
- TTL 60 秒意味着：即使不手动失效缓存，修改也最多 60 秒后生效
- `clear_pattern` 做的是子串包含匹配（`in` 操作符），不是严格前缀匹配

---

## 8. 完整集成示例

以下是一个标准插件的完整结构：

```python
# src/plugins/report_analytics/permissions.py
from src.common.permission import register_perm_point

register_perm_point("report:view", "查看报表", "查看数据分析报表", plugin_name="report_analytics")
register_perm_point("report:export", "导出报表", "导出报表数据为文件", plugin_name="report_analytics")
```

```python
# src/plugins/report_analytics/__init__.py
from nonebot import on_command
from nonebot.adapters.onebot.v11 import Bot, GroupMessageEvent
from nonebot.params import CommandArg
from nonebot.permission import SUPERUSER

# 第一步：注册权限点（import 时触发）
from . import permissions  # noqa: F401

# 第二步：使用 Matcher 级权限保护主要命令
from src.common.permission import permission_checker

view_cmd = on_command(
    "查看报表",
    permission=permission_checker("report:view") | SUPERUSER,
    priority=5,
    block=True,
)

export_cmd = on_command(
    "导出报表",
    permission=permission_checker("report:export") | SUPERUSER,
    priority=5,
    block=True,
)

@view_cmd.handle()
async def handle_view(bot: Bot, event: GroupMessageEvent):
    # ... 查看报表逻辑 ...
    await view_cmd.finish("报表数据：...")

@export_cmd.handle()
async def handle_export(bot: Bot, event: GroupMessageEvent, args: str = CommandArg()):
    # ... 导出报表逻辑 ...
    await export_cmd.finish("导出成功")
```

---

## 9. 常见陷阱与排查

### 9.1 权限点未注册

**现象**：`check_permission` 返回 False，但已在管理面板中将用户加入权限组并添加了对应 perm_key。

**原因**：插件的 `permissions.py` 未被 import，权限点没有进入 `perm_registry`。

```python
# ❌ 错误：忘记在 __init__.py 中 import permissions
# src/plugins/my_plugin/__init__.py
from . import something  # 但没有 from . import permissions

# ✅ 正确：在 __init__.py 中添加
from . import permissions  # noqa: F401
```

### 9.2 在模块顶层使用异步 API

```python
# ❌ 错误：在模块导入时调用 async 函数
from src.common.permission import check_permission
result = await check_permission(event, "my:key")  # RuntimeError！

# ✅ 正确：放在命令处理器或 async 函数内部
@cmd.handle()
async def handler(event):
    result = await check_permission(event, "my:key")
```

### 9.3 perm_key 格式不一致

注册时和检查时的 perm_key 必须**完全一致**（大小写敏感）：

```python
# 注册
register_perm_point("GroupBan:Ban", "禁言", ...)

# 检查时必须完全一致
check_permission(event, "GroupBan:Ban")    # ✅ 正确
check_permission(event, "groupban:ban")    # ❌ 不对应
check_permission(event, "group_ban:ban")   # ❌ 不对应
```

### 9.4 超级管理员的 perm_key 检查总是返回 True

`is_superuser` 在 `check()` 的最开始判断，**不检查 perm_key**。超级管理员对所有 `perm_key` 都返回 True——不存在"超级管理员没有某个权限点"的情况。

### 9.5 缓存导致修改不立即生效

```python
# 某处手动修改了数据库
async with async_session_factory() as session:
    session.add(UserBlacklist(user_id=123, reason="test", created_by=1))
    await session.commit()

# 下次校验可能仍然通过（旧缓存未失效）
# 因为绕过了管理面板，没有调用 perm_cache.clear_pattern()
```

修复：在直接操作数据库的代码中手动失效缓存：

```python
from src.common.permission import perm_cache

perm_cache.clear_pattern("perm:123:")   # 失效该用户的缓存
# 或 perm_cache.clear_all()           # 全局清空
```

### 9.6 白名单和黑名单同时存在

如果用户既在 `UserBlacklist` 又在 `UserWhitelist`，黑名单**优先**。校验流程中黑名单（步骤 1-2）在白名单（步骤 3-4）之前判断，所以会被拒绝。同样，群黑名单也优先于群白名单。

### 9.7 群绑定 vs 添加成员

| 方式 | 范围 | 命令 |
|------|------|------|
| 添加成员 | 单个用户 | `权限 权限组 添加成员 <名称> <QQ>` |
| 群绑定 | 群内**所有人** | `权限 绑定 群 <群号> <权限组名>` |

两种方式在 checker 中是**不同步骤**：添加成员在步骤 5（`PermissionGroupMember`），群绑在步骤 6（`GroupPermBinding`）。两者是 OR 关系，满足其一即放行。

### 9.8 权限组需要同时有成员和权限点

一个权限组要生效，必须同时满足：
1. **有成员**（直接添加）或**有群绑定**（群组授权）
2. **有对应的 perm_key**（通过 `添加权限` 赋予）

```bash
# QQ 管理命令操作步骤
权限 权限组 创建 admin
权限 权限组 添加权限 admin report:view report:export
权限 权限组 添加成员 admin 123456
# 或者
权限 绑定 群 789012 admin
```

---

## 10. 与其他子系统的关系

### 10.1 与 Bot DB 的关系

权限系统的所有数据（8 张表）存储在 Bot DB 中，使用 `src/common.database.async_session_factory` 获取会话。参见 **[DiTing Bot DB 操作指南](../diting-db-guide/SKILL.md)**。

### 10.2 与旧版权限系统

项目中存在旧版权限系统（如 `src/common/siqi_auth_client.py`）。新旧系统**相互独立**，不存在兼容层：

| | 新系统 | 旧系统（司契） |
|---|---|---|
| 位置 | `src/common/permission/` | `src/common/siqi_auth_client.py` |
| 存储 | Bot DB（8 张表） | 外部 HTTP 服务 |
| 模型 | 黑白名单 + 权限组 + 群绑定 | 外部 API 检查 |
| 管理 | QQ 聊天管理面板 | 外部平台 |
| 消息 | URL 白名单（如 `ban_whitelist.json`）| 各插件独立 JSON 文件 |

迁移时一个命令不能同时接入两套权限系统——选择一套即可。

---

## 快速参考卡片

### 常用导入

```python
from src.common.permission import register_perm_point     # 声明权限点
from src.common.permission import permission_checker       # Matcher 级
from src.common.permission import check_permission         # 命令式
from src.common.permission import is_superuser             # 超级管理员判断
from src.common.permission import perm_cache               # 缓存操作
```

### 标准权限点注册模板

```python
# permissions.py
from src.common.permission import register_perm_point
register_perm_point("插件名:操作", "中文名", "功能描述", plugin_name="插件名")

# __init__.py
from . import permissions  # noqa: F401
```

### 校验优先级速记

> 超级管理员 > 黑名单(用户/群) > 白名单(群/用户) > 权限组成员 + perm_key > 群绑定 + perm_key > 默认拒绝

### 管理命令速记

```
权限 黑名单 → 添加/移除/列表
权限 白名单 → 用户/群 → 添加/移除/列表
权限 权限组 → 创建/删除/列表/详情/添加成员/移除成员/添加权限/移除权限/批量加群
权限 绑定 → 群/解除/列表
权限 注册点 → 列表
权限 查看
```

---
name: perm-system-guide
description: >
  DiTing-NoneBot 权限系统集成与运维指南。
  当需要在插件中接入权限校验、注册新的权限点、通过管理面板（QQ命令或WebUI）配置黑白名单或权限组、
  排查权限拒绝问题、或理解 8 步优先级校验流程时使用。
  触发词：permission、权限、perm_key、check_permission、permission_checker、
  register_perm_point、PermissionChecker、perm_cache、TTLCache、
  白名单、黑名单、权限组、权限系统、permission_manager、
  WebUI、web管理面板、管理面板、SPA、Vue、npm run build、前端构建。
---

# DiTing 权限系统使用指南

> 完整的权限校验系统，提供 8 级优先级流程、三种接入方式、QQ 聊天管理面板 + WebUI 管理面板。
> 基于 NoneBot Plugin + OneBot v11，单进程内存缓存。

## 架构概览

```
插件代码（三种接入方式）
  │
  ├─ A) Matcher 级:  permission_checker("plugin:action")
  │                    └─ on_command(..., permission=...) 直接传入
  │
  ├─ B) 命令式:      await check_permission(event, "plugin:action")
  │                    └─ 在任意 async 函数内直接调用，返回 bool
  │                    └─ 没有 Event 的场景用 await user_has_permission(user_id, key)
  │
  └─ C) 注册点:      register_perm_point("plugin:action", "名称", "描述", plugin_name="p")
                       └─ 插件 import 时调用，启动时自动同步到数据库
       │
       ▼
src/common/permission/
  ├─ __init__.py          ← 公共 API 出口（re-export 所有关键符号）
  ├─ registry.py          ← PermissionRegistry 内存单例 → PermissionPointDef
  ├─ checker.py           ← PermissionChecker 校验引擎（8 步判断 + 缓存）
  │                          ADMIN_PERM_KEY = "permission_manager:manage"
  ├─ permission.py        ← permission_checker() → NoneBot Permission 适配器
  ├─ cache.py             ← TTLCache 内存缓存（默认 60 秒 TTL）
  ├─ supervisor.py        ← superuser_ids() —— 只是启动播种的种子，**不是鉴权入口**
  ├─ models.py            ← 9 个 SQLAlchemy 模型（8 张表）
  ├─ bootstrap.py         ← 确保 perm_admin 管理员组存在（缺失时用 SUPERUSERS 播种）
  └─ auto_register.py     ← 启动钩子：建表 + 同步权限点 + 播种管理员组
       │
       │
       ▼
src/plugins/permission_manager/          ← QQ 聊天管理面板（包，12 模块）
  ├─ __init__.py   装配：__plugin_meta__ + 导入触发注册
  ├─ runtime.py    配置 + 唯一的 perm_cmd 匹配器（其余模块都从这里取）
  ├─ dispatch.py   `权限` 子命令分发（@perm_cmd.handle()）+ 帮助文本
  ├─ login.py      登录验证码 + 二次确认（@perm_cmd.got()）
  ├─ guard.py      _invalidate_related_cache（权限缓存失效）
  ├─ blacklist.py / whitelist.py / groups.py / bindings.py / view.py
  └─ config.py / permissions.py（配置模型与权限点注册）

（参数分词与 QQ 解析已抽到 src/common/arg_parser.py，与 group_manager 共用）

src/api/
  ├─ auth.py                认证 (JWT)
  └─ permissions/           权限管理 CRUD (30 端点)
       ├─ __init__.py       父router + 鉴权
       ├─ helpers.py        分页/序列化
       ├─ schemas.py        请求模型
       └─ blacklist/whitelist/groups/bindings/points/status/cache.py
            │
            ▼
webui/
  Vue 3 + Vite SPA
  └─ 9 个管理视图
```

| 组件 | 说明 |
|---|---|
| 校验引擎 | `PermissionChecker.check()` — 8 步优先级流程，带 TTL 缓存 |
| 缓存 | `TTLCache` — 进程内内存缓存，默认 TTL 60 秒，管理操作时主动失效 |
| 注册表 | `PermissionRegistry` — 内存单例，插件 import 时收集权限点定义 |
| NoneBot 适配 | `permission_checker(perm_key)` → `Permission` 对象，直接传给 `permission=`；需要组合多个时用 NoneBot 的 `\|` |
| 启动同步 | `auto_register.py` 在 startup 时建表 + 同步 `permission_points` 表 + 播种 `perm_admin` 管理员组 |
| 管理面板 | `permission_manager` 插件（`src/plugins/permission_manager/`，12 模块的包），通过 QQ 聊天命令管理全部权限配置 |

**核心约束**：
- 权限 key 格式：`plugin_name:action`（例如 `group_ban:ban`）
- 管理操作（含 QQ 面板与 WebUI 登录）由持有 `permission_manager:manage` 权限点的用户执行 ——
  管理员判据就是这一个权限点，**不再看 `SUPERUSERS`**
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
perm 注册点/points 列表/list
perm 注册点/points 列表/list group_ban    # 按插件名筛选
```

---

## 2. 接入方式一：Matcher 级权限（推荐）

将权限检查直接绑定到 NoneBot 的 `on_command()` / `on_message()` 等 matcher 上。这是最简洁、最推荐的方式。

### 2.1 基本用法

```python
from nonebot import on_command
from src.common.permission import permission_checker

ban_cmd = on_command(
    "ban",
    permission=permission_checker("group_ban:ban"),
)
```

`permission_checker("group_ban:ban")` 返回一个 `Permission` 对象，**持有 `group_ban:ban` 权限点的用户**（以及管理员，见第 4 节第 0 步）都能触发该命令。

> 不要再写 `| SUPERUSER`：管理员判据已经是权限点（`ADMIN_PERM_KEY`），而
> `SUPERUSER` 来自 `.env`，改它必须重启。历史上 `permission_checker` 的形参没有类型注解
> 导致它根本无法使用（NoneBot 的 `Dependent.parse` 靠注解解析形参），现已修复 ——
> 改这个适配器时**务必保留 `bot: Bot, event: Event` 注解**。

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

from . import permissions  # noqa: F401 — 先注册权限点
from src.common.permission import permission_checker

ban_cmd = on_command(
    "ban",
    permission=permission_checker("group_ban:ban"),
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
┌──────────────────────────────────────────────┐
│  0. 管理员（持有 permission_manager:manage）  │ → ✅ 直接放行
├──────────────────────────────────────────────┤
│  1. 用户黑名单（UserBlacklist）               │ → ❌ 拒绝
├──────────────────────────────────────────────┤
│  2. 群黑名单（GroupBlacklist）                │ → ❌ 拒绝
├──────────────────────────────────────────────┤
│  3. 群白名单（GroupWhitelist）                │ → ✅ 完全放行（跳过后续所有检查）
├──────────────────────────────────────────────┤
│  4. 用户白名单（UserWhitelist）               │ → ✅ 完全放行（跳过后续所有检查）
├──────────────────────────────────────────────┤
│  5. 权限组成员（PermissionGroupMember）        │
│   + 匹配的 perm_key                           │ → ✅ 放行
│   所属的权限组拥有目标 perm_key               │
├──────────────────────────────────────────────┤
│  6. 群绑定（GroupPermBinding）                 │
│   + 匹配的 perm_key                           │ → ✅ 放行
│   群绑定的权限组拥有目标 perm_key             │
├──────────────────────────────────────────────┤
│  7. 默认                                       │ → ❌ 拒绝
└──────────────────────────────────────────────┘
```

> 第 0 步是**在缓存查询之前**执行的，所以它对所有 `perm_key` 都短路放行，
> 包括黑名单用户。

### 关键细节

- **管理员绕过全部检查**：判据是「持有 `ADMIN_PERM_KEY`（`permission_manager:manage`）」，
  由 `perm_admin` 权限组授予。不需要 `SUPERUSERS`——这正是为了**改权限不必重启**。
  判定结果会缓存在 `perm:{uid}:{gid}:permission_manager:manage:bypass`，键刻意复用 `perm:`
  前缀，这样管理操作里既有的 `clear_pattern("perm:{uid}:")` 能连带失效。
- **白名单是完全放行**：一旦命中群白名单或用户白名单，**不再检查 perm_key**——该用户/群的所有权限都被放行。
- **黑名单优先级高于白名单**：如果用户既在黑名单又在白名单，黑名单优先触发拒绝（步骤 1-2 在步骤 3-4 之前）。
- **权限组成员与群绑定是 OR 关系**：用户只要满足**任意一个**途径——直接是权限组成员 AND 该组拥有目标 perm_key → 通过；或所在群绑定了权限组 AND 该组拥有目标 perm_key → 通过。
- **必须同时匹配用户/群关系 AND perm_key**：用户属于某个权限组还不够——该权限组还必须**拥有被检查的 perm_key**。
- **默认拒绝**：不匹配任何规则的请求，最终返回 False。
- **整个流程使用同一个 session**：`_check_internal` 在单个 SQLAlchemy session 内完成全部查询，避免多次获取连接的开销。

### 管理员 = `perm_admin` 权限组（不再用 SUPERUSERS）

管理员就是「持有 `permission_manager:manage` 这个权限点」的用户，由名为 `perm_admin`
的权限组授予。启动时 `bootstrap.ensure_admin_group()` 负责：

- 该组**不存在** → 创建它、绑定 `permission_manager:manage`、并把 `.env` 里的
  `SUPERUSERS` 写进去作为初始成员；
- 该组**已存在** → 什么都不做。所以把成员清空后重启**不会**被重新灌回来，
  「撤销」是可靠的。

因此 `.env` 的 `SUPERUSERS` 只是**一次性种子**，改它需要重启；而增删 `perm_admin`
成员在运行期生效（缓存 TTL 内，管理操作会主动失效）——**这正是不再用 SUPERUSERS 做鉴权的原因**。

> ⚠️ 第 0 步要查库，所以 DB 不可用时管理员也会被判为无权限（fail-closed，与
> `diting_deploy._allowed` 的既有原则一致）。改造前 `is_superuser` 是纯内存判断，
> 那条「DB 挂了管理员仍能执行 `/diting restart`」的自救通道**已不存在**。

### 鉴权唯一入口

| 场景 | 用哪个 |
|---|---|
| 有 onebot Event（命令处理器、事件回调） | `await check_permission(event, perm_key)` |
| 只有 user_id（REST API、WebUI、启动脚本） | `await user_has_permission(user_id, perm_key, group_id=None)` |
| 匹配器级放行 | `permission=permission_checker(perm_key)` |
| 判断是否管理员 | 上面三种传 `ADMIN_PERM_KEY` 即可 |

**不要**再用 `is_superuser()` 做鉴权：它现在只服务于启动播种。`check_permission` 的第 0 步
本来就会为管理员短路放行，所以「先 `is_superuser` 再 `check_permission`」那种写法是多余的
（`permission_manager/guard.py` 里曾有这么一处，已删除）。

`user_has_permission(..., group_id=None)` 表示私聊语境：只统计用户的**直属**权限组成员关系，
不算群绑定（群绑定天然只在该群生效）。

---

## 5. 管理面板

权限系统提供**两种**管理界面：QQ 聊天命令（传统方式）和 WebUI 管理面板（浏览器方式）。两者操作同一套数据库，功能等价。

### 5.0 两种管理界面

| 特性 | QQ 聊天命令 | WebUI 管理面板 |
|------|-----------|---------------|
| 访问方式 | QQ 群聊发送命令 | 浏览器访问 `http://<host>:6090/` |
| 认证 | QQ 号 + 群内发言 | JWT（通过 QQ 获取临时密码登录） |
| 操作方式 | 文本命令 + 参数 | 图形表单 + 表格 + 分页 |
| 适合场景 | 快速操作、移动端 | 批量管理、数据浏览 |
| 文档 | 本节（5.1-5.8） | 参见 **[perm-webui-guide](../perm-webui-guide/SKILL.md)** |

### 5.A QQ 聊天管理命令

`permission_manager` 插件通过 QQ 聊天提供管理界面，可执行权限由 `permission_manager:manage` 权限点控制——`perm_admin` 管理员组成员默认拥有，也可通过任意权限组授予其他用户。

主命令：`权限`（别名 `perm`），帮助面板展示为 `perm`

所有子命令和操作均支持中英文别名，以下用 `A/B` 表示**两者均可**。

### 5.1 黑名单

```
perm 黑名单/blacklist 添加/add <QQ号> [原因]
perm 黑名单/blacklist 移除/remove <QQ号>
perm 黑名单/blacklist 列表/list
```

被加入黑名单的用户**所有权限均被拒绝**，且会跳过白名单检查（黑名单优先级高于白名单）。

### 5.2 白名单

用户白名单：

```
perm 白名单/whitelist 用户/user 添加/add <QQ号> [原因]
perm 白名单/whitelist 用户/user 移除/remove <QQ号>
perm 白名单/whitelist 用户/user 列表/list
```

群白名单：

```
perm 白名单/whitelist 群/group 添加/add <群号> [原因]
perm 白名单/whitelist 群/group 移除/remove <群号>
perm 白名单/whitelist 群/group 列表/list
```

白名单用户/群**完全放行所有权限**，不再检查权限组和 perm_key。

### 5.3 权限组

```
perm 权限组/group 创建/create <名称> [展示名] [描述]
perm 权限组/group 删除/delete <名称>
perm 权限组/group 列表/list
perm 权限组/group 详情/info <名称>
perm 权限组/group 添加成员/addmember <名称> <QQ> [QQ...]
perm 权限组/group 移除成员/removemember <名称> <QQ>
perm 权限组/group 添加权限/addperm <名称> <perm_key> [perm_key...]
perm 权限组/group 移除权限/removeperm <名称> <perm_key>
perm 权限组/group 批量加群/batchaddgroup <名称> <群号>
```

其中 `批量加群` 是快捷提示，实际将群内所有成员赋予权限组的功能需要通过下面 `绑定` 实现。

### 5.4 群绑定

```
perm 绑定/bind 群/group <群号> <权限组名>
perm 绑定/bind 解除/unbind <群号>
perm 绑定/bind 列表/list [群号]
```

群绑定是将一个 QQ 群**整体**与一个权限组关联。绑定后该群的**所有成员**都自动享有该权限组定义的全部权限（无需逐个添加成员）。底层在 checker 的步骤 6 中通过 `GroupPermBinding` 表查询实现。

### 5.5 注册点列表

```
perm 注册点/points 列表/list [插件名]
```

显示所有已注册的权限点（按插件分组）。可以按插件名筛选。

### 5.6 查看用户状态

```
perm 查看/view <QQ号>
```

一站式查看指定用户的权限状态：是否管理员（返回字段 `is_admin`）、是否在黑名单/白名单、所属权限组及每个组拥有的权限点。

### 5.7 登录

```
perm 登录/login
```

获取 Web 管理面板的临时登录验证码（5 分钟内有效）。执行后有**二次确认**：

1. Bot 询问「是否通过私聊发送验证码？(是/否)」
2. 回复 **是** / **y** → 验证码通过私聊发送（防止群聊泄露）
3. 回复 **否** 或任意其他内容 → 验证码直接在当前会话发送

实现上使用 NoneBot 的 `@matcher.got()` 机制等待用户确认——回复不需要匹配命令前缀，任意文本均可被捕获。验证码存储在 `perm_cache` 中（TTL 300 秒）。

### 5.8 参数解析说明

命令参数支持 `@提及` 和纯文本两种形式。解析函数 `tokenize_arguments()`（在 `src/common/arg_parser.py`，与 `group_manager` 共用同一份）将消息段拆分为 `ArgToken` 列表：`at` 类型的 token 取其 `qq` 属性，`text` 类型的 token 按空格分词；`try_parse_qq()` 再把 token 解析成 QQ 号（`text` 形式允许带前缀 `@`）。

注意 `at` 段的 `qq` 会被原样存入 token，因此**只对 str 安全**——适配器的 `MessageSegment.at()` 自身会 `str()` 归一，手工塞 int 会抛 `AttributeError`（既有缺陷，未修）。

### 5.9 缓存失效策略

所有管理操作都会通过 `_invalidate_related_cache()`（在 `src/plugins/permission_manager/guard.py`）失效相关缓存：

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

### 5.B WebUI 管理面板

WebUI 提供基于浏览器的图形化管理界面，包含 9 个管理视图，覆盖所有 QQ 命令的功能：

| 视图 | 路由 | 功能 |
|------|------|------|
| 仪表盘 | `/` | 6 张功能导航卡片 |
| 权限组 | `/groups` | 权限组 CRUD + 成员/权限点管理 |
| 群绑定 | `/bindings` | 群-权限组绑定管理 |
| 黑名单 | `/blacklist` | 用户/群黑名单（双标签页） |
| 白名单 | `/whitelist` | 用户/群白名单（双标签页） |
| 权限点 | `/points` | 已注册权限点列表（只读） |
| 用户状态 | `/user-status` | 聚合查看用户完整权限状态 |

技术栈：Vue 3 + Vite + Pico.css，通过 JWT 认证调用 `/api/v1/permissions/` 下的 REST API。

开发工作流和详细文档 → 参见 **[perm-webui-guide](../perm-webui-guide/SKILL.md)**。

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
    ADMIN_PERM_KEY,          # 管理员权限点（= permission_manager:manage）
    user_has_permission,     # 无 Event 场景的检查入口
    is_blacklisted,          # 黑名单查询（区分「被拒绝」与「无权限」）
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
- 管理面板的 `_invalidate_related_cache()`（`src/plugins/permission_manager/guard.py`）已覆盖所有内置修改场景，不需要额外处理
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
# 第一步：注册权限点（import 时触发）
from . import permissions  # noqa: F401

# 第二步：使用 Matcher 级权限保护主要命令
from src.common.permission import permission_checker

view_cmd = on_command(
    "查看报表",
    permission=permission_checker("report:view"),
    priority=5,
    block=True,
)

export_cmd = on_command(
    "导出报表",
    permission=permission_checker("report:export"),
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

### 9.4 管理员的 perm_key 检查总是返回 True

第 0 步在缓存查询之前判断「是否持有 `ADMIN_PERM_KEY`」，**不检查被查询的 perm_key**。管理员对所有 `perm_key` 都返回 True——不存在"管理员没有某个权限点"的情况。

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
| 添加成员 | 单个用户 | `perm 权限组/group 添加成员/addmember <名称> <QQ>` |
| 群绑定 | 群内**所有人** | `perm 绑定/bind 群/group <群号> <权限组名>` |

两种方式在 checker 中是**不同步骤**：添加成员在步骤 5（`PermissionGroupMember`），群绑在步骤 6（`GroupPermBinding`）。两者是 OR 关系，满足其一即放行。

### 9.8 权限组需要同时有成员和权限点

一个权限组要生效，必须同时满足：
1. **有成员**（直接添加）或**有群绑定**（群组授权）
2. **有对应的 perm_key**（通过 `添加权限` 赋予）

```bash
# QQ 管理命令操作步骤（中英文均可）
perm 权限组/group 创建/create admin
perm 权限组/group 添加权限/addperm admin report:view report:export
perm 权限组/group 添加成员/addmember admin 123456
# 或者
perm 绑定/bind 群/group 789012 admin
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
| 管理 | QQ 聊天 + WebUI 管理面板 | 外部平台 |
| 消息 | URL 白名单（如 `ban_whitelist.json`）| 各插件独立 JSON 文件 |

迁移时一个命令不能同时接入两套权限系统——选择一套即可。

---

## 快速参考卡片

### 常用导入

```python
from src.common.permission import register_perm_point     # 声明权限点
from src.common.permission import permission_checker       # Matcher 级
from src.common.permission import check_permission         # 命令式
from src.common.permission import ADMIN_PERM_KEY           # 管理员权限点
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

> 管理员 > 黑名单(用户/群) > 白名单(群/用户) > 权限组成员 + perm_key > 群绑定 + perm_key > 默认拒绝

### 管理命令速记

```
perm 黑名单/blacklist → 添加/add 移除/remove 列表/list
perm 白名单/whitelist → 用户/user 群/group → 添加/add 移除/remove 列表/list
perm 权限组/group → 创建/create 删除/delete 列表/list 详情/info 添加成员/addmember 移除成员/removemember 添加权限/addperm 移除权限/removeperm 批量加群/batchaddgroup
perm 绑定/bind → 群/group 解除/unbind 列表/list
perm 注册点/points → 列表/list
perm 查看/view
perm 登录/login
```

### WebUI 管理面板

> 浏览器图形化管理界面（9 个视图、JWT 认证、REST API）→ 参见 **[perm-webui-guide](../perm-webui-guide/SKILL.md)**

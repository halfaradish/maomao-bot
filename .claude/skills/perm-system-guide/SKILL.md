---
name: perm-system-guide
description: >
  DiTing-NoneBot 权限系统操作指南。
  当需要理解权限校验流程、添加权限点、管理黑白名单和权限组、
  排查权限相关问题时使用。
  触发词：权限、permission、perm、黑白名单、权限组、blacklist、
  whitelist、permission_group、权限点、perm_key、superuser、
  超级管理员、check_permission、permission_checker、权限校验。
---

# DiTing 权限系统操作指南

> 位于 `src/common/permission/` — 统一的权限校验核心，替代了分散的 Siqi auth + JSON 白名单方案。

## 架构概览

```
src/common/permission/
├── __init__.py        # 公共 API：check_permission, permission_checker, register_perm_point, is_superuser
├── models.py          # 9 个 SQLAlchemy 模型，8 张表（继承 Bot DB 的 Base）
├── checker.py         # 权限校验引擎（完整优先级链）
├── permission.py      # NoneBot Permission 适配器（包装为 on_command 的 permission= 参数）
├── supervisor.py      # 超级管理员判断（读取 NoneBot 的 SUPERUSERS 配置）
├── registry.py        # 内存权限点注册表（插件 import 时收集，启动时同步 DB）
├── cache.py           # 内存 TTL 缓存（默认 60s）
└── auto_register.py   # 启动钩子：建表 + 同步权限点到数据库
```

### 核心文件导航

| 文件 | 关键内容 | 位置 |
|---|---|---|
| 校验入口 | `check_permission(event, perm_key)` | `checker.py:132` |
| NoneBot 适配器 | `permission_checker(perm_key)` → `NB_Permission` | `permission.py:12` |
| 超级管理员 | `is_superuser(user_id)` → 读 `driver.config.superusers` | `supervisor.py:9` |
| 注册权限点 | `register_perm_point(key, name, ...)` | `registry.py:58` |
| 缓存单例 | `perm_cache` (TTLCache, 60s TTL) | `cache.py:52` |
| 启动同步 | `sync_permission_points()` | `auto_register.py:18` |

### 管理面板

| 项目 | 位置 |
|---|---|
| 插件目录 | `src/plugins/permission_manager/` |
| 主逻辑（867 行） | `src/plugins/permission_manager/__init__.py` |
| 配置模型 | `src/plugins/permission_manager/config.py` |

所有管理命令在 **QQ 群聊** 中以 `权限`（别名 `perm`）触发，仅超级管理员可执行。

---

## 1. 超级管理员（Superuser）

超级管理员使用 **NoneBot 内置的 `SUPERUSERS` 配置**（`supervisor.py:11` 通过 `driver.config.superusers` 读取），**不查数据库**。

在 `.env` / `.env.{ENVIRONMENT}` 中配置（半角逗号分隔的 QQ 号）：

```env
SUPERUSERS=10001,10002
```

### 校验优先级

超级管理员在权限校验的第 **0 优先级**（`checker.py:44-46`）：

```python
# checker.py:44 — 超级管理员绕过所有检查（不缓存）
if is_superuser(user_id):
    return True
```

超级管理员不受黑白名单、权限组限制，**总是放行**。

---

## 2. 权限校验全流程

**完整优先级链**（`checker.py:4-13`，在 `PermissionChecker.check()` 中实现）：

```
1. 超级管理员           → 直接放行（不缓存）
2. 用户黑名单           → 拒绝
3. 群黑名单             → 拒绝
4. 群白名单             → 完全放行
5. 用户白名单           → 完全放行
6. 权限组成员           → 检查 perm_key
7. 群绑定权限组         → 检查 perm_key
8. 默认拒绝
```

### 关键实现细节（`checker.py`）

- **入口**：`check(event, perm_key)` (`:37`)
- **缓存**：先检查 `perm_cache`，命中直接返回 (`:49-52`)
- **单次 DB 事务**：`_check_internal()` 使用单个 `async_session_factory()` 会话完成所有查询 (`:65`)
- **权限组检查**：`_check_permission_groups()` 同时检查用户所属组 (`:101-106`) 和群绑定组 (`:109-114`)

---

## 3. 三种接入方式

### A) Matcher 级权限（推荐）

```python
from src.common.permission import permission_checker
from nonebot.permission import SUPERUSER

ban_cmd = on_command(
    "ban",
    permission=permission_checker("group_ban:ban") | SUPERUSER,
)
```

`permission_checker()` 返回 `nonebot.permission.Permission` 实例，可与 `SUPERUSER` 等用 `|` 组合。

### B) 命令式（函数内联检查）

```python
from src.common.permission import check_permission

@ban_cmd.handle()
async def handler(bot: Bot, event: GroupMessageEvent):
    if not await check_permission(event, "group_ban:ban"):
        await ban_cmd.finish("你没有权限")
    # ... 执行后续逻辑
```

### C) 声明权限点（插件加载时注册）

创建 `permissions.py`：

```python
from src.common.permission import register_perm_point

register_perm_point(
    "group_ban:ban",        # perm_key, 格式: plugin_name:action
    "禁言",                 # 名称
    "禁言群成员",            # 描述（可选）
    plugin_name="group_ban",  # 来源插件名（可选）
)
```

然后在 `__init__.py` 中触发注册：

```python
from . import permissions  # noqa: F401
```

权限点会在 bot 启动时由 `auto_register.py` 自动同步到数据库（`permission_points` 表），无需手动建表。

---

## 4. 数据库模型

所有模型定义在 `src/common/permission/models.py` 中，继承 Bot DB 的 `Base`。

| # | 模型类 | MySQL 表名 | 用途 | 关键约束 |
|---|--------|-----------|------|---------|
| 1 | `PermissionPoint` | `permission_points` | 权限点注册 | `perm_key` UNIQUE |
| 2 | `UserBlacklist` | `user_blacklist` | 用户黑名单 | `user_id` UNIQUE |
| 3 | `GroupBlacklist` | `group_blacklist` | 群黑名单 | `group_id` UNIQUE |
| 4 | `UserWhitelist` | `user_whitelist` | 用户白名单 | `user_id` UNIQUE |
| 5 | `GroupWhitelist` | `group_whitelist` | 群白名单 | `group_id` UNIQUE |
| 6 | `PermissionGroup` | `permission_groups` | 权限组定义 | `name` UNIQUE |
| 7 | `PermissionGroupMember` | `permission_group_members` | 权限组成员 | UNIQUE(`group_id`, `user_id`) |
| 8 | `PermissionGroupPerm` | `permission_group_perms` | 权限组-权限绑定 | UNIQUE(`group_id`, `perm_key`) |
| 9 | `GroupPermBinding` | `group_perm_bindings` | QQ群-权限组绑定 | UNIQUE(`qq_group_id`, `permission_group_id`) |

### 4.1 导入方式

```python
from src.common.permission.models import (
    UserBlacklist, GroupBlacklist,
    UserWhitelist, GroupWhitelist,
    PermissionGroup, PermissionGroupMember, PermissionGroupPerm,
    GroupPermBinding,
)
```

因为模型继承的是 `src.common.database.Base`，它们存储在 **Bot DB**（`diting_qq_bot`）中。

### 4.2 建表与同步

由 `auto_register.py` 在 Bot 启动时自动执行（`@get_driver().on_startup`）：

1. 调用 `Base.metadata.create_all` 创建不存在的表（幂等）
2. 将 `perm_registry` 中收集的权限点同步到 `permission_points` 表（按 `perm_key` 去重）

---

## 5. 管理面板命令

所有命令通过 `权限`（别名 `perm`）触发，在 QQ 群聊中由超级管理员执行。

### 5.1 黑名单

| 子操作 | 语法 | 说明 |
|--------|------|------|
| 添加 | `权限 黑名单 添加 <QQ号> [原因]` | 加入黑名单，之后拒绝所有操作 |
| 移除 | `权限 黑名单 移除 <QQ号>` | 从黑名单移除 |
| 列表 | `权限 黑名单 列表` | 列出所有黑名单用户 |

**缓存失效**：添加/移除操作会清除该用户的缓存条目。

### 5.2 白名单

| 子操作 | 语法 | 说明 |
|--------|------|------|
| 用户 添加 | `权限 白名单 用户 添加 <QQ号> [原因]` | 加入用户白名单（完全放行） |
| 用户 移除 | `权限 白名单 用户 移除 <QQ号>` | 移除 |
| 用户 列表 | `权限 白名单 用户 列表` | 列出所有用户白名单 |
| 群 添加 | `权限 白名单 群 添加 <群号> [原因]` | 加入群白名单（群内所有人放行） |
| 群 移除 | `权限 白名单 群 移除 <群号>` | 移除 |
| 群 列表 | `权限 白名单 群 列表` | 列出所有群白名单 |

**行为**：白名单在检查优先级中位于黑名单之后、权限组之前。被加入白名单的用户或群，其所有操作完全放行（不检查 perm_key）。

### 5.3 权限组（Role 系统）

| 子操作 | 语法 | 说明 |
|--------|------|------|
| 创建 | `权限 权限组 创建 <名称> [展示名] [描述]` | 创建权限组 |
| 删除 | `权限 权限组 删除 <名称>` | 删除权限组（级联删除成员和权限关联） |
| 列表 | `权限 权限组 列表` | 列出所有权限组 |
| 详情 | `权限 权限组 详情 <名称>` | 查看权限组的成员和权限列表 |
| 添加成员 | `权限 权限组 添加成员 <名称> <QQ> [QQ...]` | 将用户加入权限组 |
| 移除成员 | `权限 权限组 移除成员 <名称> <QQ>` | 从权限组移除用户 |
| 添加权限 | `权限 权限组 添加权限 <名称> <perm_key> [perm_key...]` | 向权限组授予权限点 |
| 移除权限 | `权限 权限组 移除权限 <名称> <perm_key>` | 从权限组撤销权限点 |

**行为**：用户如果属于某个权限组，或者用户所在群绑定到某个权限组，则该用户获得该权限组的所有 `perm_key`。

### 5.4 群绑定

| 子操作 | 语法 | 说明 |
|--------|------|------|
| 绑定 | `权限 绑定 群 <群号> <权限组名>` | 将 QQ 群绑定到权限组 |
| 解除 | `权限 绑定 解除 <群号>` | 解除群的所有绑定 |
| 列表 | `权限 绑定 列表 [群号]` | 列出所有绑定 |

**行为**：绑定的群内所有成员自动获得权限组的所有权限。

### 5.5 注册点

| 子操作 | 语法 | 说明 |
|--------|------|------|
| 列表 | `权限 注册点 列表 [插件名]` | 列出所有注册的权限点（可按插件名筛选） |

### 5.6 查看

| 子操作 | 语法 | 说明 |
|--------|------|------|
| 查看 | `权限 查看 <QQ号>` | 查看用户的完整权限状态（超级管理员→黑名单→白名单→权限组→默认拒绝） |

---

## 6. 缓存机制

由 `cache.py` 中的 `TTLCache` 实现（默认 60 秒 TTL）。

```python
from src.common.permission.cache import perm_cache

# 获取缓存值（过期返回 None）
result = perm_cache.get("perm:123456:789000:group_ban:ban")

# 设置缓存
perm_cache.set("perm:123456:789000:group_ban:ban", True)

# 按前缀清除（管理操作时使用）
perm_cache.clear_pattern("perm:123456:")

# 清空所有（权限组变更时使用）
perm_cache.clear_all()
```

### 缓存失效策略

| 操作类型 | 失效范围 | 说明 |
|---------|---------|------|
| 用户黑名单添加/移除 | 清除该用户的 `perm:<user_id>:*` | 最小粒度 |
| 群黑名单添加/移除 | 清除该群的 `perm:*:<group_id>:*` | 影响该群所有用户 |
| 用户白名单添加/移除 | 清除该用户的 `perm:<user_id>:*` | — |
| 群白名单添加/移除 | 清除该群的 `perm:*:<group_id>:*` | — |
| 权限组创建/删除/成员变更 | `perm_cache.clear_all()` | 影响范围不可精确预测 |
| 权限组权限变更 | `perm_cache.clear_all()` | — |
| 群绑定/解除 | `perm_cache.clear_all()` | 影响所有该群用户 |

---

## 7. 权限点命名规范

`perm_key` 遵循 `plugin_name:action` 格式：

| 示例 | 含义 |
|------|------|
| `group_ban:ban` | 禁言权限 |
| `group_ban:unban` | 解禁权限 |
| `auto_manage_group:kick` | 踢人权限 |
| `group_file_manager:delete` | 删除文件权限 |

---

## 8. 常见问题 / 注意事项

### 8.1 超级管理员不走数据库

`is_superuser()` 完全依赖 `driver.config.superusers`（`.env` 配置），**不查询数据库**。如果需要在数据库中管理超级管理员，需要二次开发（当前不支持）。

### 8.2 缓存不命中时自动回源

缓存过期（60s）或未命中时，自动执行完整的 DB 查询流程并回填缓存。这是通过 `check()` 方法中的缓存检查 + `_check_internal()` 调用链实现的。

### 8.3 管理命令使用直接 SQLAlchemy

`permission_manager` 插件通过 `async_session_factory()` 直接执行 SQLAlchemy 操作（`select`、`add`、`delete`），**不使用** `crud.py` 包装器。因为管理操作涉及联表、原子清除等复杂场景，CRUD 包装器不够灵活。

### 8.4 超级管理员使用 `|` 组合

当使用 `permission_checker()` 时，建议始终与 `SUPERUSER` 组合，以防止超级管理员被权限系统误拦：

```python
permission=permission_checker("my_plugin:action") | SUPERUSER
```

不组合的话，超级管理员的绕过逻辑**仅在 `check_permission` 内部生效**，而 `permission_checker` 包装器本身不会自动注入 SUPERUSER，需手动组合。

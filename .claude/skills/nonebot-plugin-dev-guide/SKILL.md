---
name: nonebot-plugin-dev-guide
description: >
  DiTing-NoneBot NoneBot 插件开发指南。
  当需要创建新插件、为现有插件添加功能、注册命令/事件处理器、
  集成权限系统或数据库、配置 APScheduler 定时任务、
  或理解项目通用开发规范时使用。
  触发词：插件、plugin、on_command、on_notice、on_request、on_message、
  PluginMetadata、matcher、handler、config、pydantic、BaseModel、
  权限、permission、check_permission、权限点、permission_checker、
  数据库、database、async_session_factory、CRUD、SQLAlchemy、
  APScheduler、定时任务、scheduler、require、禁用、ENABLED、
  PluginGroupEnum、PluginBadgeColor、send_forward_msg、JsonUtils、
  rate_limiter、令牌桶、group_ban、like、contest_reminder、group_sentinel、
  permission_manager、插件开发、创建插件、新建插件、NoneBot插件、
  get_plugin_config、事件处理器、bot.send、bot.call_api、driver、
  on_startup、on_bot_connect、scheduler.scheduled_job、ActionFailed、
  MessageSegment、CommandArg、T_State。
---

# DiTing-NoneBot 插件开发指南

> NoneBot 2 + OneBot V11 — 基于项目实际代码的插件开发规范与最佳实践。

**核心原则**：本项目插件开发围绕三个核心约定展开 —— 正确的 `PluginMetadata` 声明、规范的 `get_plugin_config` 配置加载、以及严格的 `FinishedException` 异常处理。所有插件自动发现于 `src/plugins/` 目录，无需手动注册。

## 1. 插件架构概览

### 1.1 项目结构

```
src/
├── plugins/                  # 35+ NoneBot 插件（自动发现）
│   └── <plugin_name>/
│       ├── __init__.py       # 入口：PluginMetadata + 命令/事件处理器
│       ├── config.py         # Pydantic 配置类（可选）
│       └── permissions.py    # 权限点注册（可选）
├── common/                   # 共享层工具
│   ├── database.py           # SQLAlchemy 异步引擎 + session 工厂
│   ├── crud.py               # Django 风格 CRUD 包装器
│   ├── models/               # SQLAlchemy ORM 模型 (botdb, icpc, like)
│   ├── model/model.py        # PluginGroupEnum, PluginBadgeColor 枚举
│   └── permission/           # 权限系统（8 级优先级检查）
└── config/                   # 全局配置类
```

### 1.2 插件发现机制

[pyproject.toml](../../pyproject.toml) 的 `[tool.nonebot]` 段声明插件发现路径：

```toml
[tool.nonebot]
plugin_dirs = ["src/plugins"]           # NoneBot 自动扫描此目录下所有 Python 包
plugins = [                             # 外部插件（pip 安装的）
    "nonebot_plugin_apscheduler",
    "nonebot_plugin_prometheus",
    "nonebot_plugin_alconna"
]
builtin_plugins = ["echo"]
```

**无需手动注册** — 将目录放到 `src/plugins/` 下即可被自动发现加载。

### 1.3 插件组织结构模式

项目中常见的四种插件结构：

| 模式 | 文件数 | 示例插件 | 适用场景 |
|------|-------|---------|---------|
| **单文件** | 仅 `__init__.py` | group_ban, mass_kick, refer_collector | 逻辑简单，命令少于 3 个 |
| **双文件** | `__init__.py` + `config.py` | leaderboard, group_card_changer | 需要配置的单体插件 |
| **多文件** | 入口 + config + 逻辑模块 | todo_reminder, auto_manage_group, contest_reminder | 复杂业务，多命令/多事件 |
| **瘦入口** | 极简 `__init__.py` + 主模块 | check_up（`check_up.py` 含 PluginMetadata）, like（`like.py` 含 PluginMetadata） | PluginMetadata 不放在 `__init__.py` |

选择哪种模式取决于插件复杂度。大多数插件使用**双文件**或**多文件**模式。

### 1.4 插件分组与徽章

定义在 [src/common/model/model.py](../../src/common/model/model.py)：

| 枚举成员 | `.value` | 分类 | 典型插件 |
|---------|----------|------|---------|
| `PluginGroupEnum.BASE` | `"基础命令"` | 基础命令 | cmd_list |
| `PluginGroupEnum.GROUP_MANAGE` | `"群管理"` | 群管理功能 | group_ban, permission_manager, group_sentinel |
| `PluginGroupEnum.CONTEST` | `"竞赛相关"` | ICPC 竞赛 | contest_reminder, sub_records, duel |
| `PluginGroupEnum.UTILITY` | `"实用工具"` | 实用工具 | like, todo_reminder, refer_collector |
| `PluginGroupEnum.MONITOR` | `"监控提醒"` | 监控与提醒 | check_up, logging_info |

| 枚举成员 | `.value` |
|---------|----------|
| `PluginBadgeColor.GREEN` | `"green"` |
| `PluginBadgeColor.BLUE` | `"blue"` |
| `PluginBadgeColor.YELLOW` | `"yellow"` |

## 2. 创建新插件 — 分步指南

### Step 1: 创建目录

```bash
mkdir -p src/plugins/<plugin_name>
touch src/plugins/<plugin_name>/__init__.py
```

命名约定：**snake_case**（如 `my_new_feature`），描述性强。

### Step 2: 编写 PluginMetadata

在 `__init__.py` 中声明插件元信息：

```python
from nonebot.plugin import PluginMetadata
from src.common.model.model import PluginGroupEnum, PluginBadgeColor

__plugin_meta__ = PluginMetadata(
    name="插件显示名",
    description="插件功能的一句话描述",
    usage="用法说明（可多行，\n分隔）",
    config=Config,                      # 可选，无配置可省略
    supported_adapters={"~onebot.v11"},  # 必填
    extra={
        "group": PluginGroupEnum.UTILITY.value,      # 必填
        "badge_color": PluginBadgeColor.GREEN.value,  # 必填
    },
)
```

`extra` 字段中的 `group` 和 `badge_color` 是**强制约定**，供 `/help` 菜单系统（[cmd_list 插件](../cmd_list/get_plugin_usage.py)）读取展示。

### Step 3: 创建 config.py（如需配置）

```python
# src/plugins/<plugin_name>/config.py
from pydantic import BaseModel, Field
from typing import List, Optional

class Config(BaseModel):
    """插件配置 — 字段自动从环境变量加载"""
    my_priority: int = 10                # 有默认值的可选字段
    my_block: bool = True
    my_cmd: str = "mycommand"            # 命令触发词
    my_enable: bool                      # 无默认值 = 必须从环境变量提供
    my_list: List[str] = Field(default_factory=list)
```

Pydantic 字段名**自动映射**为大写环境变量（`my_priority` → `MY_PRIORITY`）。在 `__init__.py` 中加载：

```python
from nonebot import get_plugin_config
from .config import Config

config = get_plugin_config(Config)
```

### Step 4: 注册命令/事件处理器

```python
from nonebot import on_command

my_cmd = on_command(
    "命令名",
    aliases={"别名1", "别名2"},  # 可选
    priority=10,                # 数字越小优先级越高（5=核心, 10=常规, 30=低优）
    block=True,                 # True=阻止其他 matcher 继续处理
)
```

### Step 5: 实现处理器

```python
from nonebot.adapters.onebot.v11 import Bot, GroupMessageEvent, Message
from nonebot.params import CommandArg
from nonebot.exception import FinishedException
from nonebot import logger

@my_cmd.handle()
async def handle_my_cmd(bot: Bot, event: GroupMessageEvent, args: Message = CommandArg()):
    raw = args.extract_plain_text().strip()
    if not raw:
        await my_cmd.finish("请提供参数")    # finish() 发送消息并结束

    try:
        # ... 业务逻辑 ...
        await my_cmd.finish("操作成功")
    except FinishedException:
        raise                               # 必须重新抛出！
    except Exception as e:
        logger.error(f"[my_plugin] 操作失败: {e}", exc_info=True)
        await my_cmd.finish("操作失败，请重试")
```

### Step 6: 可选集成

- **数据库**：在 handler 内使用 `async with async_session_factory() as session:` 访问 Bot DB
- **权限**：创建 `permissions.py` 注册权限点，handler 中调用 `check_permission()`
- **定时任务**：使用 `require("nonebot_plugin_apscheduler")` + scheduler

## 3. PluginMetadata 完整参考

### 3.1 字段说明

| 字段 | 类型 | 必填 | 说明 |
|------|------|------|------|
| `name` | `str` | 是 | 插件显示名（中文），如 "群聊禁言" |
| `description` | `str` | 是 | 一句话功能描述 |
| `usage` | `str` | 是 | 使用方法，多行用 `\n` 或三引号 |
| `config` | `BaseModel subclass` | 否 | Pydantic 配置类引用 |
| `type` | `str` | 否 | 默认 `"application"` |
| `supported_adapters` | `set[str]` | **是** | 固定 `{"~onebot.v11"}` |
| `extra` | `dict` | **是** | 必须包含 `group` 和 `badge_color` |

### 3.2 extra 字段

| 键 | 类型 | 来源 | 必填 |
|----|------|------|------|
| `group` | `str` | `PluginGroupEnum.XXX.value` | 是 |
| `badge_color` | `str` | `PluginBadgeColor.XXX.value` | 是 |
| `author` | `str` | 自定义 | 否 |
| `version` | `str` | 自定义 | 否 |

### 3.3 实例对照

**简单版** (from [group_ban/__init__.py](../../src/plugins/group_ban/__init__.py))：

```python
__plugin_meta__ = PluginMetadata(
    name="群聊禁言",
    description="通过白名单控制, 允许指定用户/群组使用禁言和踢人功能",
    usage="@bot ban @成员 60 —— 禁言指定成员60秒\n@bot unban @成员 —— 解除指定成员禁言\n@bot kick @成员 —— 踢出指定成员",
    config=Config,
    type="application",
    supported_adapters={"~onebot.v11"},
    extra={
        "group": PluginGroupEnum.GROUP_MANAGE.value,
        "badge_color": PluginBadgeColor.BLUE.value
    },
)
```

**复杂版** (from [permission_manager/__init__.py](../../src/plugins/permission_manager/__init__.py))：

```python
__plugin_meta__ = PluginMetadata(
    name="权限管理",
    description="权限系统的 QQ 聊天管理面板，支持黑/白名单、权限组、群绑定等全部管理操作",
    usage=(
        "perm 黑名单/blacklist 添加/add <QQ号> [原因]\n"
        "perm 黑名单/blacklist 移除/remove <QQ号>\n"
        # ... 更多子命令 ...
        "perm 登录/login - 获取Web管理面板登录验证码（二次确认）"
    ),
    config=Config,
    supported_adapters={"~onebot.v11"},
    extra={
        "group": PluginGroupEnum.GROUP_MANAGE.value,
        "badge_color": PluginBadgeColor.BLUE.value,
    },
)
```

## 4. 配置模式

### 4.1 Pydantic 配置类模板

```python
from pydantic import BaseModel, Field
from typing import List, Optional

class Config(BaseModel):
    """
    插件配置
    字段名自动映射为大写环境变量（my_field → MY_FIELD）
    """
    # 有默认值 = 可选
    my_priority: int = 10
    my_block: bool = True
    my_cmd: str = "mycommand"

    # 无默认值 = 必须从环境变量读取
    my_api_key: str
    my_enable: bool

    # 复杂类型
    my_platforms: List[str] = Field(default_factory=list)
```

### 4.2 加载配置

```python
from nonebot import get_plugin_config
from .config import Config

config = get_plugin_config(Config)  # 在模块级别调用，不在 handler 内部
```

### 4.3 示例

**简单配置** (from [group_ban/config.py](../../src/plugins/group_ban/config.py))：

```python
class Config(BaseModel):
    group_ban_cmd: str = "ban"
    group_unban_cmd: str = "unban"
    group_ban_priority: int = 10
    group_ban_block: bool = True
```

**复杂配置** (from [contest_reminder/config.py](../../src/plugins/contest_reminder/config.py))：

```python
class Config(BaseModel):
    clist_gci_enable: bool
    clist_schedule_job_enable: bool
    clist_gci_priority: int
    clist_gci_cmd: str = '比赛提醒'
    clist_hours_ahead: int
    clist_max_hours_ahead: int
    clist_username: str
    clist_api_key: str
    clist_contest_fetch_base_url: str
    clist_platforms: List[str]
    clist_filename: str
    clist_remind_run_time_hour: int
```

## 5. 命令与事件处理

### 5.1 on_command — QQ 指令处理

这是最常用的模式。注册一个 QQ 群聊命令：

```python
from nonebot import on_command
from nonebot.adapters.onebot.v11 import Bot, GroupMessageEvent, Message
from nonebot.params import CommandArg

my_cmd = on_command("命令名", aliases={"别名"}, priority=10, block=True)

@my_cmd.handle()
async def handle(bot: Bot, event: GroupMessageEvent, args: Message = CommandArg()):
    text = args.extract_plain_text().strip()
    await my_cmd.finish(f"收到参数: {text}")
```

**优先级约定**：`5`（管理/核心命令）、`10`（常规命令）、`30`（低优先级）。

**多命令插件** (from [like/like.py](../../src/plugins/like/like.py))：

```python
like_me = on_command("赞我", permission=GROUP, priority=plugin_config.priority, block=plugin_config.block)
like_other = on_command("赞他", aliases={"赞她", "超市"}, permission=GROUP, priority=plugin_config.priority, block=plugin_config.block)
like_follow = on_command("订阅赞", aliases={"dev-订阅赞"}, permission=GROUP, priority=plugin_config.priority, block=plugin_config.block)
like_unfollow = on_command("取消订阅赞", permission=GROUP, priority=plugin_config.priority, block=plugin_config.block)
```

**自定义 Rule** (from [group_ban/__init__.py](../../src/plugins/group_ban/__init__.py)) — 确保命令是独立单词而非子串：

```python
from nonebot.rule import Rule

def _is_word_boundary_command(cmd: str):
    async def _rule(event: GroupMessageEvent) -> bool:
        if not isinstance(event, GroupMessageEvent):
            return False
        msg_text = event.get_plaintext().strip()
        if not msg_text.lower().startswith(cmd.lower()):
            return False
        if len(msg_text) == len(cmd):
            return True
        next_char = msg_text[len(cmd)]
        if next_char in (' ', '\t', '\n', '@', '，', '。', '！', '？', '、', '：', '；'):
            return True
        if not next_char.isalnum():
            return True
        return False
    return Rule(_rule)

ban_cmd = on_command("ban", rule=_is_word_boundary_command("ban"), priority=10, block=True)
```

### 5.2 on_notice — 事件监听

用于监听群事件（上传文件、成员变动等）：

```python
from nonebot import on_notice
from nonebot.adapters.onebot.v11 import GroupUploadNoticeEvent, GroupIncreaseNoticeEvent, GroupDecreaseNoticeEvent

# 群文件上传 (from group_file_manager)
upload_notice = on_notice()

@upload_notice.handle()
async def handle_group_upload(bot: Bot, event: GroupUploadNoticeEvent):
    file_info = event.file
    logger.info(f"[新文件] {event.group_id}: {file_info.name}")
    # ... 下载处理 ...

# 成员加入/退出 (from auto_manage_group)
member_join = on_notice()

@member_join.handle()
async def handle_member_join(bot: Bot, event: GroupIncreaseNoticeEvent):
    await bot.send_group_msg(group_id=event.group_id, message=f"欢迎 {event.user_id} 加入！")
```

### 5.3 on_request — 请求处理

用于处理加群请求等 (from [group_sentinel/__init__.py](../../src/plugins/group_sentinel/__init__.py))：

```python
from nonebot import on_request
from nonebot.adapters.onebot.v11 import Bot, GroupRequestEvent
from nonebot.rule import Rule

def is_group_add(event) -> bool:
    return isinstance(event, GroupRequestEvent) and event.sub_type == "add"

group_request = on_request(rule=Rule(is_group_add), priority=5, block=False)

@group_request.handle()
async def _(bot: Bot, event: GroupRequestEvent):
    group_id = event.group_id
    user_id = event.user_id
    comment = event.comment

    approved, reason = await audit_join_request(comment, user_id, group_id)
    if approved:
        await event.approve(bot)
    else:
        await event.reject(bot, reason=reason)
```

### 5.4 on_message — 消息拦截

用于无条件监听所有消息（日志、监控等）：

```python
from nonebot import on_message
from nonebot.adapters.onebot.v11 import GroupMessageEvent, PrivateMessageEvent
from nonebot.rule import Rule

def is_any_event(event):
    return isinstance(event, (GroupMessageEvent, PrivateMessageEvent))

message_listen = on_message(priority=999, block=False, rule=Rule(is_any_event))

@message_listen.handle()
async def handle_all_messages(event):
    logger.info(f"[message] {event.user_id}: {event.get_plaintext()}")
```

### 5.5 原始 API 调用

常用 OneBot API 的便捷方法和原始调用：

```python
# 便捷方法
await bot.set_group_ban(group_id=group_id, user_id=target_user, duration=60)
await bot.set_group_kick(group_id=group_id, user_id=target_user)
await bot.get_group_member_info(group_id=group_id, user_id=user_id, no_cache=True)
await bot.get_group_list()

# 原始 API 调用（高级功能）
await bot.call_api("send_group_forward_msg", group_id=group_id, messages=message_nodes)
await bot.call_api("set_group_card", group_id=group_id, user_id=user_id, card="新名片")
```

### 5.6 Matcher 方法速查

| 方法 | 行为 | 使用场景 |
|------|------|---------|
| `matcher.finish("msg")` | 发送消息 + 结束处理器（引发 `FinishedException`） | 操作完成、用户级错误 |
| `matcher.send("msg")` | 发送消息 + 继续执行 | 进度提示 |
| `matcher.pause("msg")` | 发送消息 + 等待用户再次输入 | 多步交互 |
| `matcher.got("key", prompt="...")` | 获取用户输入并存入 state | 获取多步参数（如 permission_manager 登录确认） |
| `matcher.reject("msg")` | 拒绝输入 + 重新等待 | 输入验证失败 |

## 6. 数据库操作

### 6.1 Bot DB — SQLAlchemy 异步操作

Bot DB 通过 `async_session_factory` 访问：

```python
from sqlalchemy import select
from src.common.database import async_session_factory
from src.common.models.botdb_models import Group

async with async_session_factory() as session:
    # 查询
    result = await session.execute(
        select(Group).where(Group.group_id == group_id).limit(1)
    )
    group = result.scalars().first()

    # 创建
    new_group = Group(group_id=123, group_name="群名")
    session.add(new_group)
    await session.commit()

    # 更新
    group.group_name = "新群名"
    await session.commit()

    # 删除 (from sqlalchemy import delete as sa_delete)
    result = await session.execute(sa_delete(Group).where(Group.group_id == group_id))
    await session.commit()
```

### 6.2 CRUD 包装器

来自 [src/common/crud.py](../../src/common/crud.py) 的 5 个便捷函数，支持**Django 风格过滤器**：

| 函数 | 签名 | 用途 |
|------|------|------|
| `async_create_record` | `(model_cls, **fields) → obj` | 创建单条记录 |
| `async_get_one` | `(model_cls, **filters) → obj \| None` | 查询单条 |
| `async_get_many` | `(model_cls, filters=None, order_by=None, limit=None) → list` | 查询多条 |
| `async_update_records` | `(model_cls, filters, updates) → count` | 批量更新 |
| `async_delete_records` | `(model_cls, **filters) → count` | 批量删除 |

**过滤器语法**（Django `__` 风格）：

| 后缀 | SQL 等价 | 示例 |
|------|---------|------|
| `__in` | `IN (...)` | `{"user_id__in": [1, 2, 3]}` |
| `__lte` / `__lt` | `<=` / `<` | `{"created_at__lte": yesterday}` |
| `__gte` / `__gt` | `>=` / `>` | `{"score__gte": 60}` |
| `__icontains` | `LIKE '%val%'` (不区分大小写) | `{"name__icontains": "test"}` |
| `__contains` | `LIKE '%val%'` | `{"tag__contains": "python"}` |
| `__startswith` | `LIKE 'val%'` | `{"name__startswith": "A"}` |

**使用示例**：

```python
from src.common.crud import async_create_record, async_get_many
from src.common.models.botdb_models import MessageEventLog

# 创建
record = await async_create_record(MessageEventLog,
    message_id=123, user_id=456, raw_message="hello")

# 多条查询（含过滤器 + 排序 + 限制）
logs = await async_get_many(
    MessageEventLog,
    filters={"group_id": group_id, "raw_message__icontains": "关键词"},
    order_by=["-time"],    # 前缀 - 表示降序
    limit=20
)
```

### 6.3 ICPC 数据库

ICPC 竞赛数据库是独立的 MySQL 数据库，有两种访问方式：

```python
# 方式 1: 异步 (SQLAlchemy)
from src.common.icpc_database import icpc_async_session_factory
from src.common.models.icpc_models import IcpcUser

# 方式 2: 同步 (原始 SQL，用于遗留代码)
from src.common.icpc_db_pool import get_icpc_db_connection
```

**注意**：Bot DB 和 ICPC DB 是**不同的 MySQL 数据库** — 不可交叉查询。

### 6.4 模型文件参考

| 文件 | 基类 | 表数量 | 用途 |
|------|------|-------|------|
| [models/botdb_models.py](../../src/common/models/botdb_models.py) | `Base` (from database.py) | 13 | Bot 主数据库 |
| [models/icpc_models.py](../../src/common/models/icpc_models.py) | `IcpcBase` (from icpc_database.py) | 6 | 竞赛数据库 |
| [models/like_plugin_models.py](../../src/common/models/like_plugin_models.py) | `Base` | 2 | 点赞插件 |

## 7. 权限系统接入

### 7.1 三种集成方式

**方式 A：Matcher 级权限（推荐）**

```python
from nonebot.permission import SUPERUSER
from src.common.permission import permission_checker

my_cmd = on_command(
    "cmd",
    permission=permission_checker("my_plugin:action") | SUPERUSER,
    priority=5, block=True,
)
```

**方式 B：命令式检查（handler 内）**

```python
from src.common.permission import check_permission

@my_cmd.handle()
async def handle(event: GroupMessageEvent):
    if not await check_permission(event, "my_plugin:action"):
        await my_cmd.finish("你没有权限")
    # ... 正常逻辑 ...
```

**方式 C：声明权限点**

创建 `permissions.py` 注册权限点到系统：

```python
# src/plugins/my_plugin/permissions.py
from src.common.permission import register_perm_point

register_perm_point(
    "my_plugin:action",        # perm_key: plugin_name:action
    "功能名称",                 # 中文显示名
    "功能描述",                 # 详细说明
    plugin_name="my_plugin",   # 来源插件
)
```

然后在 `__init__.py` 中导入以触发注册：

```python
from . import permissions  # noqa: F401
```

**权限键命名约定**：`plugin_name:action`（如 `group_sentinel:audit`、`auto_manage_group:increase`）。

### 7.2 检查优先级

权限检查按以下 8 级优先级执行（在 [checker.py](../../src/common/permission/checker.py) 中实现）：

1. **超级管理员** → 直接放行
2. **用户黑名单** → 拒绝
3. **群黑名单** → 拒绝
4. **群白名单** → 完全放行
5. **用户白名单** → 完全放行
6. **权限组成员** → 检查 perm_key
7. **群绑定权限组** → 检查 perm_key
8. **默认拒绝**

### 7.3 实际示例

完整例子参见 [group_sentinel/permissions.py](../../src/plugins/group_sentinel/permissions.py)：

```python
from src.common.permission import register_perm_point

register_perm_point(
    "group_sentinel:audit",
    "入群审核",
    "审核用户加群请求，根据入群回答判断是否放行",
    plugin_name="group_sentinel",
)
```

群级功能检查使用 `is_group_feature_enabled()`（来自 [auto_manage_group/group_checker.py](../../src/plugins/auto_manage_group/group_checker.py)），它实现了一条轻量级的检查链（仅群白名单 + GroupPermBinding）：

```python
from ..auto_manage_group.group_checker import is_group_feature_enabled

if not await is_group_feature_enabled(group_id, "group_sentinel:audit"):
    return  # 该群未启用此功能
```

## 8. 定时任务

### 8.1 require 模式

```python
from nonebot import require

try:
    require("nonebot_plugin_apscheduler")
except (ValueError, RuntimeError):
    pass  # NoneBot 初始化前会抛出，在启动后总是可用

from nonebot_plugin_apscheduler import scheduler
```

### 8.2 两种注册方式

**方式 1：装饰器**（适用于静态定时任务）

```python
@scheduler.scheduled_job("cron", hour=8, minute=0, second=0, id="daily_job")
async def daily_task():
    bot = get_bot()
    await bot.send_group_msg(group_id=123, message="每日提醒")
```

**方式 2：`add_job` 编程式**（适用于动态任务，如每个比赛生成一个提醒）

```python
from uuid import uuid4

# Cron 任务
scheduler.add_job(
    contest_reminder,
    "cron",
    hour=config.clist_remind_run_time_hour,
    minute=0, second=0,
    id="contests_reminder"
)

# 一次性 date 任务
scheduler.add_job(
    remind_contest_to_groups,
    "date",
    run_date=contest.start - timedelta(hours=1),
    args=[contest],
    id=f"contest_reminder_{uuid4().hex}"
)
```

### 8.3 完整示例

From [contest_reminder/__init__.py](../../src/plugins/contest_reminder/__init__.py)：

```python
from nonebot import require, get_bot
require("nonebot_plugin_apscheduler")
from nonebot_plugin_apscheduler import scheduler

async def contest_reminder():
    contests = contest_fetcher.fetch_contests(platform_names=config.clist_platforms)
    for contest in contests:
        run_date = contest.start - timedelta(hours=1)
        scheduler.add_job(
            remind_contest_to_groups,
            "date", run_date=run_date, args=[contest],
            id=f"contest_reminder_{uuid4().hex}"
        )

if config.clist_schedule_job_enable:
    scheduler.add_job(contest_reminder, "cron",
        hour=config.clist_remind_run_time_hour,
        minute=0, second=0, id="contests_reminder")
```

**关键点**：
- `id` 必须全局唯一 — 动态任务使用 `uuid4().hex`
- 用配置变量控制是否启用定时任务（`if config.xxx_schedule_enable:`）
- 定时任务中通过 `bot = get_bot()` 获取 bot 实例

## 9. 插件启停控制

### 9.1 标准禁用模式

使用环境变量控制插件开关，禁用时提供存根 `__plugin_meta__`（不产生 RuntimeError）：

```python
import os

from nonebot import logger

# 在模块顶层读取环境变量
MY_PLUGIN_ENABLED = os.getenv("MY_PLUGIN_ENABLED", "true").lower() == "true"

if not MY_PLUGIN_ENABLED:
    __plugin_meta__ = PluginMetadata(
        name="我的插件（已禁用）",
        description="功能描述（当前已禁用，设置 MY_PLUGIN_ENABLED=true 启用）",
        usage="此插件已在环境变量中禁用",
        supported_adapters={"~onebot.v11"},
        extra={
            "group": PluginGroupEnum.UTILITY.value,
            "badge_color": PluginBadgeColor.GREEN.value,
        },
    )
    logger.info(f"[my_plugin] 插件已禁用 (MY_PLUGIN_ENABLED=false)")
    # 不注册任何 handler，不加载配置
else:
    # ===== 正常插件代码 =====
    __plugin_meta__ = PluginMetadata(
        name="我的插件",
        description="...",
        usage="...",
        config=Config,
        supported_adapters={"~onebot.v11"},
        extra={
            "group": PluginGroupEnum.UTILITY.value,
            "badge_color": PluginBadgeColor.GREEN.value,
        },
    )
    # 所有 handler、数据库逻辑、调度器在此
```

### 9.2 关键规则

- 禁用时必须提供 `__plugin_meta__` 存根（NoneBot 加载器需要）
- 禁用存根的 name 应带 `（已禁用）` 后缀
- 禁用存根**不包含** `config=Config`
- 禁用时应输出日志提示插件已关闭
- 正常代码必须在 `else` 分支内（不会执行到）
- 环境变量命名：`PLUGIN_NAME_ENABLED`

### 9.3 实际示例

- [group_file_manager/__init__.py](../../src/plugins/group_file_manager/__init__.py) — `GROUP_FILE_MANAGER_ENABLED`
- [group_sentinel/__init__.py](../../src/plugins/group_sentinel/__init__.py) — `GROUP_SENTINEL_ENABLED`
- [icpc_ac_monitor/__init__.py](../../src/plugins/icpc_ac_monitor/__init__.py) — `ICPC_AC_MONITOR_ENABLED`

## 10. 导入约定

### 10.1 两种导入风格

项目中间同时存在两种导入风格，任一均可接受，但在同一插件内应保持一致：

```python
# 风格 A：相对导入（插件深处较常用）
from .config import Config
from ...common.database import async_session_factory
from ...common.models.botdb_models import MonitoredGroup

# 风格 B：绝对导入（核心类型建议使用）
from src.common.model.model import PluginGroupEnum, PluginBadgeColor
from src.common.permission import check_permission, register_perm_point
```

### 10.2 常用导入块模板

```python
# ── NoneBot 核心 ──
from nonebot import (
    get_plugin_config, on_command, on_notice, on_request, on_message,
    logger, get_driver, require, get_bot
)

# ── 适配器类型 ──
from nonebot.adapters.onebot.v11 import (
    Bot, GroupMessageEvent, PrivateMessageEvent, Message, MessageSegment
)
from nonebot.adapters.onebot.v11 import (
    GroupUploadNoticeEvent, GroupIncreaseNoticeEvent,
    GroupDecreaseNoticeEvent, GroupRequestEvent
)

# ── 参数与状态 ──
from nonebot.params import CommandArg
from nonebot.typing import T_State

# ── 异常 ──
from nonebot.exception import FinishedException
from nonebot.adapters.onebot.v11.exception import ActionFailed

# ── 插件元数据 ──
from nonebot.plugin import PluginMetadata
from src.common.model.model import PluginGroupEnum, PluginBadgeColor

# ── 配置 ──
from pydantic import BaseModel, Field
from typing import List, Optional

# ── 数据库 ──
from src.common.database import async_session_factory
from sqlalchemy import select, delete as sa_delete, func

# ── 权限 ──
from src.common.permission import check_permission, permission_checker, register_perm_point

# ── 通用工具 ──
from ...common import JsonUtils
from src.common.send_forward_msg import send_forward_msg
```

## 11. 常用工具速查

| 模块 | 导入 | 用途 |
|------|------|------|
| `database.py` | `from ...common.database import async_session_factory` | Bot DB SQLAlchemy 异步会话 |
| `crud.py` | `from src.common.crud import async_create_record, async_get_many` | Django 风格 CRUD 包装器 |
| `send_forward_msg.py` | `from ...common.send_forward_msg import send_forward_msg` | 合并转发消息（群聊+私聊） |
| `utils.py` | `from ...common.utils import BuildUri, QQAvatarLoader` | NapCat 文件 URI、QQ 头像 |
| `json_utils.py` | `from ...common import JsonUtils` | 线程安全的 JSON 文件读写 |
| `rate_limiter.py` | `from ...common.rate_limiter import TokenBucketLimiter, GroupRateLimiter` | 令牌桶限速器 |
| `timer.py` | `from ...common.timer import timer, timed_section` | 性能计时上下文管理器 |
| `icpc_db_pool.py` | `from ...common import get_icpc_db_connection` | ICPC DB 原始 SQL 连接 |
| `oj_redis_pool.py` | `from ...common import get_redis_connection` | Redis 连接池 |
| `compress_pics.py` | `from ...common import CompressPic` | 图片压缩 |

### JsonUtils 使用

```python
from ...common import JsonUtils

# 读取（有默认值）
data, _ = JsonUtils.read("my_data.json", {"key": []})

# 写入
JsonUtils.write("my_data.json", data)
```

文件默认存储在 `data/` 目录下。

### send_forward_msg 使用

```python
from ...common.send_forward_msg import send_forward_msg

# 简单模式：消息列表按行拆分
msg_list = ["消息1", "消息2", "消息3"]
await send_forward_msg.by_onebot_api(
    bot, event, msg_list,
    group_id=str(event.group_id)
)

# 自定义发送者模式
from ...common.send_forward_msg import SenderInfo
senders = [
    SenderInfo(user_id="123", nickname="Alice", message=Message("Hello")),
]
await send_forward_msg.custom_sender_by_onebot_api(
    bot, event, senders,
    group_id=str(event.group_id)
)
```

## 12. 日志与错误处理

### 12.1 日志规范

使用 NoneBot 的 logger（loguru 包装器）：

```python
from nonebot import logger

# 级别（从低到高）
logger.trace("最详细")
logger.debug("调试信息")
logger.info("正常信息")
logger.warning("警告，非致命")
logger.error("错误")
logger.critical("严重错误")

# 带插件标识（推荐约定）
logger.info(f"[my_plugin] 操作成功，参数: {param}")
logger.warning(f"[my_plugin] 已禁用 (MY_PLUGIN_ENABLED=false)")

# 带堆栈追踪
logger.opt(exception=True).error(f"[my_plugin] 处理失败: {e}")
```

文件日志在 [bot.py](../../bot.py) 中配置：每日轮转，保留 7 天，压缩为 zip。

**注意**：Docker 环境中 `print()` 作为日志兜底（`logger` 输出可能被缓冲）。

### 12.2 错误处理模式

**标准 Handler 错误处理**：

```python
from nonebot.exception import FinishedException
from nonebot.adapters.onebot.v11.exception import ActionFailed
from nonebot import logger

@my_cmd.handle()
async def handle(bot: Bot, event: GroupMessageEvent, args: Message = CommandArg()):
    try:
        # ... 主要业务逻辑 ...
        await my_cmd.finish("操作成功")
    except FinishedException:
        raise                               # ⚠️ 必须重新抛出！
    except ActionFailed as e:
        if getattr(e, 'retcode', None) == 121:  # 权限不足
            await my_cmd.finish("机器人权限不足，无法执行此操作")
        else:
            raise
    except Exception as e:
        logger.opt(exception=True).error(f"[my_plugin] 错误: {e}")
        await my_cmd.finish("操作失败，请重试")
```

**DB 操作错误处理**：

```python
async with async_session_factory() as session:
    try:
        session.add(record)
        await session.commit()
    except Exception as e:
        await session.rollback()
        logger.opt(exception=True).error(f"[my_plugin] DB 写入失败: {e}")
        raise
```

**调度器循环错误处理**：

```python
while self.running:
    try:
        await self._check_and_execute()
        await asyncio.sleep(self.interval)
    except asyncio.CancelledError:
        break
    except Exception as e:
        logger.error(f"[my_plugin] 调度器错误: {e}")
        await asyncio.sleep(self.interval)  # 出错后继续，不崩溃
```

**`FinishedException` 规则（最重要）**：
- `matcher.finish()` 会引发 `FinishedException` 来终止处理器链
- 所有 `except Exception` 块**必须**先单独捕获并重新抛出 `FinishedException`
- 这条规则违反是项目中最常见的 bug

## 13. Driver 生命周期钩子

```python
from nonebot import get_driver

driver = get_driver()

@driver.on_startup
async def _():
    """Bot 启动时执行一次"""
    # 数据库初始化、缓存预热、默认数据创建
    await _ensure_fk_migration()
    logger.info("[my_plugin] 启动初始化完成")

@driver.on_shutdown
async def _():
    """Bot 关闭时执行一次"""
    # 资源清理
    logger.info("[my_plugin] 已关闭")

@driver.on_bot_connect
async def _(bot: Bot):
    """每个 bot 连接时执行"""
    # 同步群列表、注册定时任务
    group_list = await bot.get_group_list()
    logger.info(f"[my_plugin] bot 已连接，在 {len(group_list)} 个群中")
```

**实际示例**：

| 插件 | 钩子 | 用途 |
|------|------|------|
| group_file_manager | `on_startup` + `on_bot_connect` | FK 迁移、群同步、每日爬取注册 |
| group_sentinel | `on_startup` | 创建默认权限组 |
| group_statistics | `on_startup` + `on_shutdown` | 启动/关闭日志 |
| auto_manage_group | `on_startup` | 初始化数据、注册 MQTT |

## 14. 插件参考速查表

| 插件 | 展示的模式 | 适用场景 |
|------|-----------|---------|
| [group_ban](../../src/plugins/group_ban/) | on_command, 自定义 Rule, FinishedException 处理 | 纯命令插件参考 |
| [like](../../src/plugins/like/) | 多命令+别名, 数据库直接访问, APScheduler | DB + 调度器模式 |
| [contest_reminder](../../src/plugins/contest_reminder/) | on_command + add_job cron/date, 合并转发 | 定时任务密集型 |
| [group_sentinel](../../src/plugins/group_sentinel/) | 权限点注册, 禁用模式, on_request, 启动钩子 | 生产级多模式插件 |
| [permission_manager](../../src/plugins/permission_manager/) | 复杂命令解析, 完整 DB CRUD, 缓存管理, matcher.got | 权限系统集成 |
| [logging_info](../../src/plugins/logging_info/) | on_message 监听, DAO 模式, 事件序列化 | 消息日志机器人 |
| [todo_reminder](../../src/plugins/todo_reminder/) | 多模块插件, 自然语言解析, 调度器集成 | 复杂业务逻辑 |
| [group_file_manager](../../src/plugins/group_file_manager/) | 禁用模式, on_notice (upload), 条件导入, FK 迁移 | 文件管理 + 条件加载 |
| [auto_manage_group](../../src/plugins/auto_manage_group/) | 权限集成, on_notice (join/leave), 多特性 | 功能完整的群管理 |
| [cmd_list](../../src/plugins/cmd_list/) | /help 菜单, 模板渲染 | 标准 BASE 组插件参考 |

## 15. 测试与调试

### 15.1 本地运行

```bash
nb run    # 启动 NoneBot（端口 6090）
```

查看控制台输出确认插件加载成功。在测试 QQ 群中发送命令验证行为。

### 15.2 调试技巧

- 使用 `logger.info()` 输出关键变量和流程节点
- Docker 日志查看：`docker compose logs -f` 或 `./scripts/docker-manager.sh logs`
- `test/` 目录包含临时测试脚本（ad-hoc，无 pytest 框架），可参考但不能直接运行

### 15.3 常见错误排查

| 错误现象 | 可能原因 | 解决方法 |
|---------|---------|---------|
| 插件未加载 | 目录不在 plugin_dirs 中 | 检查 [pyproject.toml](../../pyproject.toml) → `plugin_dirs = ["src/plugins"]` |
| 配置未加载 | 环境变量名与字段名不匹配 | 检查 config.py 字段名，环境变量自动为大写 |
| FinishedException 被吞 | `except Exception` 捕获了 `FinishedException` | 在所有 handler 中添加 `except FinishedException: raise` |
| 数据库查询在加载时失败 | 模块级代码中创建了 session | 将数据库操作移到 async handler 函数内部 |
| 权限总是拒绝 | `permissions.py` 未被导入 | 在 `__init__.py` 中添加 `from . import permissions  # noqa: F401` |
| APScheduler 不可用 | `require` 调用在 NoneBot 初始化之前 | 使用 `try/except (ValueError, RuntimeError)` 包裹 |
| 日志不输出 | 日志级别设置过高 | 检查 [bot.py](../../bot.py) 中 `logger.add` 的 `level` 参数 |
| 插件生成的文件误触发热重载 | 运行时缓存/数据文件写入 `src/`，被 watcher 检测到变更 | 将写入路径改为 `data/` 目录，或在项目根目录的 `.watchignore` 中添加忽略关键字 |

## 16. 新插件检查清单

创建新插件时依次检查：

- [ ] `src/plugins/<name>/__init__.py` 存在并包含 `PluginMetadata`
- [ ] `PluginMetadata.supported_adapters` 设置为 `{"~onebot.v11"}`
- [ ] `PluginMetadata.extra` 包含正确的 `group`（`PluginGroupEnum` 枚举）和 `badge_color`
- [ ] 如需配置，创建 `config.py` 并定义 Pydantic `Config` 类
- [ ] 使用 `get_plugin_config(Config)` 在模块级别加载配置
- [ ] 命令处理器使用 `on_command()` 注册，设置合适的优先级
- [ ] 事件处理器使用 `on_notice()` / `on_request()` 注册
- [ ] 所有 handler 正确处理 `FinishedException`（单独的 `except` 子句，重新抛出）
- [ ] 数据库操作在 async handler 函数内部使用 `async_session_factory`
- [ ] 如接入权限：创建 `permissions.py` 注册权限点，handler 中调用 `check_permission()`
- [ ] 如使用定时任务：正确 `require("nonebot_plugin_apscheduler")`，job ID 全局唯一
- [ ] 如需启停控制：实现 `_ENABLED` 环境变量检查 + 禁用存根 `__plugin_meta__`
- [ ] 日志使用 `logger.info(f"[plugin_name] ...")` 格式，异常使用 `logger.opt(exception=True)`
- [ ] 目录命名使用 snake_case
- [ ] 如插件在 `src/` 下生成运行时文件（缓存、数据记录等），将写入路径改为 `data/` 目录 或 在项目根 `.watchignore` 中添加忽略关键字，避免误触发热重载

## 17. 相关 Skills

- **[diting-db-guide](../diting-db-guide/SKILL.md)** — Bot DB SQLAlchemy 操作：CRUD 包装器、过滤器语法、模型参考
- **[icpc-db-guide](../icpc-db-guide/SKILL.md)** — ICPC 竞赛数据库：原始 SQL 查询、`get_icpc_db_connection`、`%s` 占位符
- **[perm-system-guide](../perm-system-guide/SKILL.md)** — 权限系统：8 级检查、`check_permission`、黑白名单、权限组、WebUI
- **[webui-dev-guide](../webui-dev-guide/SKILL.md)** — WebUI 前端开发（React 19 + HeroUI）：管理面板页面与 API

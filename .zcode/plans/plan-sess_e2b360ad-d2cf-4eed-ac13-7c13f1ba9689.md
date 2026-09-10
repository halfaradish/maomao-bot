## 问题根因

`权限111` 会误触发「是否通过私聊发送验证码？」是**两个缺陷叠加**的结果：

1. **`on_command` 变成了裸前缀匹配。**
   `.env.local:7` 配置了 `COMMAND_START=["/", ""]`，空字符串也是合法命令前缀；而 `__init__.py:194` 的 `on_command` 没有传 `force_whitespace`。于是 NoneBot 用 `TrieRule.longest_prefix` 把 `权限111` 匹配为「命令 `权限` + 参数 `111`」（见 nonebot `rule.py:106`、`rule.py:387`：`force_whitespace=None` 时直接返回 True，不要求空格）。同理 `permxxx`、`permanent` 也会命中。

2. **子命令 `if/elif` 链没有兜底 `else`。**
   `handle_permission_command`（`__init__.py:219-315`）对未知子命令 `111` 没有任何分支命中，函数**没有调用 `finish()` 就正常返回了**。NoneBot 于是继续执行同一个 matcher 的下一个 handler —— `@perm_cmd.got("login_confirm", ...)`（`__init__.py:317`）。`got` 的 `_key_getter` 依赖在 handler 函数体**之前**运行，state 里没有 `login_confirm`，就直接 `matcher.reject(prompt)` 发出验证码提示（nonebot `matcher.py:520-527`）。`__init__.py:320` 那句 `if not state.get("login_ready")` 守卫永远来不及执行，所以形同虚设。

## 修复方案（已按「完全静默忽略」确认）

只需改 `src/plugins/permission_manager/__init__.py` 两处：

**1. 命令必须与参数间有空白符**（`__init__.py:194-199`）
```python
perm_cmd = on_command(
    config.perm_mgr_command,
    aliases={'perm'},
    force_whitespace=True,          # 新增
    priority=config.perm_mgr_priority,
    block=config.perm_mgr_block,
)
```
效果：`权限111`、`permxxx` 不再是命令，直接静默忽略；`权限`、`/权限 黑名单`、`perm 登录` 等现有用法（均带空格或不带参数）不受影响。

**2. 未知子命令静默结束，禁止落到 `got` 二次确认**（`__init__.py:315` 之后）
```python
    # ---- help ----
    elif subcmd in ("help", "帮助", "-h", "--help"):
        await perm_cmd.finish(_build_help_text())

    else:
        # 未知子命令：静默结束，避免落入 login_confirm 的 got 提示
        await perm_cmd.finish()
```
效果：`权限 abc`（带空格但子命令非法）静默不回复，也不会再出现验证码提示；`权限 登录` 仍走正常二次确认流程。

## 验证要点
- `权限111` / `perm111` / `permanent` → 无任何回复。
- `权限 abc` → 无任何回复。
- `权限`（无参数）→ 仍输出帮助。
- `权限 登录` → 仍提示「是否通过私聊发送验证码？(是/否)」，回复「是/否」流程不变。
- 其余各子命令（黑名单/白名单/权限组/绑定/注册点/查看/help）行为不变。

## 影响面
仅改动该插件的 matcher 注册与子命令分支，不触碰全局 `COMMAND_START`、不涉及数据库与权限逻辑，风险低。无现有测试文件，验证以手动触发命令为主。
"""`权限` / `perm` 命令的子命令分发。

本模块的 `@perm_cmd.handle()` 必须在 `login.py` 的 `@perm_cmd.got(...)` 之前生效，
详见「登录」分支里的延迟导入说明。
"""
from nonebot.adapters.onebot.v11 import Bot, Message, MessageEvent
from nonebot.params import CommandArg
from nonebot.typing import T_State
from nonebot import logger

from src.common.arg_parser import tokenize_arguments
from src.common.permission import ADMIN_PERM_KEY, check_permission

from .runtime import perm_cmd
from .blacklist import _blacklist_add, _blacklist_list, _blacklist_remove
from .bindings import _binding_add, _binding_list, _binding_remove
from .groups import (
    _perm_group_add_member,
    _perm_group_add_perm,
    _perm_group_batch_add_group,
    _perm_group_create,
    _perm_group_delete,
    _perm_group_detail,
    _perm_group_list,
    _perm_group_remove_member,
    _perm_group_remove_perm,
)
from .view import _list_permission_points, _view_user_permissions
from .whitelist import _whitelist_add, _whitelist_list, _whitelist_remove


def _build_help_text() -> str:
    return (
        "perm 命令可用操作（也支持中文）:\n"
        "━━━ 黑名单/blacklist ━━━\n"
        "perm 黑名单 添加/add <QQ号> [原因]\n"
        "perm 黑名单 移除/remove <QQ号>\n"
        "perm 黑名单 列表/list\n"
        "━━━ 白名单/whitelist ━━━\n"
        "perm 白名单 用户/user 添加/add <QQ号> [原因]\n"
        "perm 白名单 用户/user 移除/remove <QQ号>\n"
        "perm 白名单 用户/user 列表/list\n"
        "perm 白名单 群/group 添加/add <群号> [原因]\n"
        "perm 白名单 群/group 移除/remove <群号>\n"
        "perm 白名单 群/group 列表/list\n"
        "━━━ 权限组/group ━━━\n"
        "perm 权限组 创建/create <名称> [展示名] [描述]\n"
        "perm 权限组 删除/delete <名称>\n"
        "perm 权限组 列表/list\n"
        "perm 权限组 详情/info <名称>\n"
        "perm 权限组 添加成员/addmember <名称> <QQ> [QQ...]\n"
        "perm 权限组 移除成员/removemember <名称> <QQ>\n"
        "perm 权限组 添加权限/addperm <名称> <perm_key> [perm_key...]\n"
        "perm 权限组 移除权限/removeperm <名称> <perm_key>\n"
        "perm 权限组 批量加群/batchaddgroup <名称> <群号>\n"
        "━━━ 群绑定/bind ━━━\n"
        "perm 绑定 群/group <群号> <权限组名>\n"
        "perm 绑定 解除/unbind <群号>\n"
        "perm 绑定 列表/list [群号]\n"
        "━━━ 其他 ━━━\n"
        "perm 注册点/points 列表/list [插件名]\n"
        "perm 查看/view <QQ号>\n"
        "perm 登录/login - 获取Web管理面板登录验证码"
    )


@perm_cmd.handle()
async def handle_permission_command(
    bot: Bot,
    event: MessageEvent,
    args: Message = CommandArg(),
    state: T_State = T_State(),
):
    # 需要管理员权限（持有 permission_manager:manage 权限点）
    if not await check_permission(event, ADMIN_PERM_KEY):
        logger.warning(f"用户 {event.user_id} 尝试执行权限管理命令但权限不足")
        await perm_cmd.finish("你没有权限管理权限系统（仅超级管理员或拥有「权限管理」权限的用户可执行）")

    logger.info(f"用户 {event.user_id} 执行权限管理命令: {args.extract_plain_text().strip()}")
    tokens = tokenize_arguments(args)
    if not tokens:
        await perm_cmd.finish(_build_help_text())

    subcmd = tokens[0].value
    rest = tokens[1:]

    # ---- 黑名单 / blacklist ----
    if subcmd in ("黑名单", "blacklist", "bl"):
        if not rest:
            await perm_cmd.finish("用法: perm 黑名单/blacklist 添加/add 移除/remove 列表/list")
        op = rest[0].value
        if op in ("添加", "add"):
            await _blacklist_add(event, rest[1:], "user")
        elif op in ("移除", "remove", "rm"):
            await _blacklist_remove(event, rest[1:], "user")
        elif op in ("列表", "list", "ls"):
            await _blacklist_list(event, "user")
        else:
            await perm_cmd.finish(f"未知操作: {op}，可用: 添加/add 移除/remove 列表/list")

    # ---- 白名单 / whitelist ----
    elif subcmd in ("白名单", "whitelist", "wl"):
        if not rest:
            await perm_cmd.finish("用法: perm 白名单/whitelist 用户/user 群/group 添加/add 移除/remove 列表/list")
        scope = rest[0].value
        if scope in ("用户", "user"):
            scope = "用户"
        elif scope in ("群", "group"):
            scope = "群"
        else:
            await perm_cmd.finish("请指定范围: 用户/user 或 群/group")
        if len(rest) < 2:
            await perm_cmd.finish(f"用法: perm 白名单/whitelist {scope} 添加/add 移除/remove 列表/list")
        op = rest[1].value
        if op in ("添加", "add"):
            await _whitelist_add(event, rest[2:], scope)
        elif op in ("移除", "remove", "rm"):
            await _whitelist_remove(event, rest[2:], scope)
        elif op in ("列表", "list", "ls"):
            await _whitelist_list(event, scope)
        else:
            await perm_cmd.finish(f"未知操作: {op}，可用: 添加/add 移除/remove 列表/list")

    # ---- 权限组 / group ----
    elif subcmd in ("权限组", "group", "pg"):
        if not rest:
            await perm_cmd.finish("用法: perm 权限组/group 创建/create 删除/delete 列表/list 详情/info 添加成员/addmember 移除成员/removemember 添加权限/addperm 移除权限/removeperm 批量加群/batchaddgroup")
        op = rest[0].value
        if op in ("创建", "create"):
            await _perm_group_create(event, rest[1:])
        elif op in ("删除", "delete", "del"):
            await _perm_group_delete(event, rest[1:])
        elif op in ("列表", "list", "ls"):
            await _perm_group_list(event)
        elif op in ("详情", "info", "detail"):
            await _perm_group_detail(event, rest[1:])
        elif op in ("添加成员", "addmember"):
            await _perm_group_add_member(event, rest[1:])
        elif op in ("移除成员", "removemember", "rmmember"):
            await _perm_group_remove_member(event, rest[1:])
        elif op in ("添加权限", "addperm"):
            await _perm_group_add_perm(event, rest[1:])
        elif op in ("移除权限", "removeperm", "rmperm"):
            await _perm_group_remove_perm(event, rest[1:])
        elif op in ("批量加群", "batchaddgroup"):
            await _perm_group_batch_add_group(event, rest[1:])
        else:
            await perm_cmd.finish("未知操作，可用: 创建/create 删除/delete 列表/list 详情/info 添加成员/addmember 移除成员/removemember 添加权限/addperm 移除权限/removeperm 批量加群/batchaddgroup")

    # ---- 绑定 / bind ----
    elif subcmd in ("绑定", "bind"):
        if not rest:
            await perm_cmd.finish("用法: perm 绑定/bind 群/group 解除/unbind 列表/list")
        op = rest[0].value
        if op in ("群", "group"):
            await _binding_add(event, rest[1:])
        elif op in ("解除", "unbind", "remove"):
            await _binding_remove(event, rest[1:])
        elif op in ("列表", "list", "ls"):
            await _binding_list(event, rest[1:])
        else:
            await perm_cmd.finish("未知操作，可用: 群/group 解除/unbind 列表/list")

    # ---- 注册点 / points ----
    elif subcmd in ("注册点", "points", "permpoint"):
        if not rest or rest[0].value not in ("列表", "list", "ls"):
            await perm_cmd.finish("用法: perm 注册点/points 列表/list [插件名]")
        await _list_permission_points(event, rest[1:])

    # ---- 查看 / view ----
    elif subcmd in ("查看", "view", "check"):
        await _view_user_permissions(event, rest)

    # ---- 登录 / login ----
    elif subcmd in ("登录", "login", "signin"):
        # 延迟导入：login 的模块体会注册 @perm_cmd.got("login_confirm")，它必须排在
        # 本模块的 @perm_cmd.handle() 之后；顶层导入会让 login 先于本模块执行。
        from .login import _handle_login
        await _handle_login(bot, event, state)

    # ---- help ----
    elif subcmd in ("help", "帮助", "-h", "--help"):
        await perm_cmd.finish(_build_help_text())

    else:
        # 未知子命令：静默结束，避免落入 login_confirm 的 got 提示
        await perm_cmd.finish()

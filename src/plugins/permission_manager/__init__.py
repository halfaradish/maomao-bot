"""
权限管理面板插件

通过 QQ 聊天命令管理整个权限系统，全部操作仅超级管理员可执行。

命令格式: 权限 <子命令> [参数...]
"""
from dataclasses import dataclass
from typing import List, Optional

from nonebot import get_driver, get_plugin_config, on_command
from nonebot.adapters.onebot.v11 import Bot, Message, MessageEvent, GroupMessageEvent
from nonebot.params import CommandArg
from nonebot.plugin import PluginMetadata
from nonebot.exception import FinishedException

from sqlalchemy import select, delete as sa_delete
from sqlalchemy.orm import selectinload

from src.common.database import async_session_factory
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
from src.common.permission.cache import perm_cache
from src.common.permission import check_permission
from src.common.permission.supervisor import is_superuser
from src.common.model.model import PluginGroupEnum, PluginBadgeColor
from .config import Config
from . import permissions  # noqa: F401

__plugin_meta__ = PluginMetadata(
    name="权限管理",
    description="权限系统的 QQ 聊天管理面板，支持黑/白名单、权限组、群绑定等全部管理操作",
    usage=(
        "perm 黑名单/blacklist 添加/add <QQ号> [原因]\n"
        "perm 黑名单/blacklist 移除/remove <QQ号>\n"
        "perm 黑名单/blacklist 列表/list\n"
        "perm 白名单/whitelist 用户/user 添加/add <QQ号> [原因]\n"
        "perm 白名单/whitelist 用户/user 移除/remove <QQ号>\n"
        "perm 白名单/whitelist 用户/user 列表/list\n"
        "perm 白名单/whitelist 群/group 添加/add <群号> [原因]\n"
        "perm 白名单/whitelist 群/group 移除/remove <群号>\n"
        "perm 白名单/whitelist 群/group 列表/list\n"
        "perm 权限组/group 创建/create <名称> [展示名] [描述]\n"
        "perm 权限组/group 删除/delete <名称>\n"
        "perm 权限组/group 列表/list\n"
        "perm 权限组/group 详情/info <名称>\n"
        "perm 权限组/group 添加成员/addmember <名称> <QQ> [QQ...]\n"
        "perm 权限组/group 移除成员/removemember <名称> <QQ>\n"
        "perm 权限组/group 添加权限/addperm <名称> <perm_key> [perm_key...]\n"
        "perm 权限组/group 移除权限/removeperm <名称> <perm_key>\n"
        "perm 权限组/group 批量加群/batchaddgroup <名称> <群号>\n"
        "perm 绑定/bind 群/group <群号> <权限组名>\n"
        "perm 绑定/bind 解除/unbind <群号>\n"
        "perm 绑定/bind 列表/list [群号]\n"
        "perm 注册点/points 列表/list [插件名]\n"
        "perm 查看/view <QQ号>"
    ),
    config=Config,
    supported_adapters={"~onebot.v11"},
    extra={
        "group": PluginGroupEnum.GROUP_MANAGE.value,
        "badge_color": PluginBadgeColor.BLUE.value,
    },
)

config = get_plugin_config(Config)
driver = get_driver()


# ============================================================
# 工具函数
# ============================================================


@dataclass
class ArgToken:
    kind: str  # "text" | "at"
    value: str


def _tokenize_arguments(message: Message) -> List[ArgToken]:
    """将消息拆分为 token 列表（at / text）"""
    tokens: List[ArgToken] = []
    for seg in message:
        if seg.type == "text":
            text = seg.data.get("text", "")
            for part in text.replace("\n", " ").split():
                if part:
                    tokens.append(ArgToken("text", part))
        elif seg.type == "at":
            qq = seg.data.get("qq")
            if qq and qq not in ("all", "0"):
                tokens.append(ArgToken("at", qq))
    return tokens


def _try_parse_qq(token: ArgToken) -> Optional[int]:
    """尝试从 token 解析 QQ 号（at 或纯数字）"""
    if token.kind == "at" and token.value.isdigit():
        return int(token.value)
    if token.kind == "text":
        text = token.value.lstrip("@")
        if text.isdigit():
            return int(text)
    return None


async def _ensure_superuser(event: MessageEvent) -> bool:
    """检查是否有权限管理权限系统"""
    if is_superuser(event.user_id):
        return True
    return await check_permission(event, "permission_manager:manage")


def _invalidate_related_cache(user_id: Optional[int] = None, group_id: Optional[int] = None):
    """失效相关缓存"""
    if user_id is not None:
        perm_cache.clear_pattern(f"perm:{user_id}:")
    if group_id is not None:
        perm_cache.clear_pattern(f"perm::{group_id}:")
    # 全局失效兜底（权限组变更影响范围不可精确预测）
    if user_id is None and group_id is None:
        perm_cache.clear_all()


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
        "perm 查看/view <QQ号>"
    )


# ============================================================
# 命令入口
# ============================================================

perm_cmd = on_command(
    config.perm_mgr_command,
    aliases={'perm'},
    priority=config.perm_mgr_priority,
    block=config.perm_mgr_block,
)


@perm_cmd.handle()
async def handle_permission_command(
    bot: Bot,
    event: MessageEvent,
    args: Message = CommandArg(),
):
    # 需要超级管理员或 permission_manager:manage 权限
    if not await _ensure_superuser(event):
        await perm_cmd.finish("你没有权限管理权限系统（仅超级管理员或拥有「权限管理」权限的用户可执行）")

    tokens = _tokenize_arguments(args)
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

    # ---- help ----
    elif subcmd in ("help", "帮助", "-h", "--help"):
        await perm_cmd.finish(_build_help_text())




# ============================================================
# 黑名单操作
# ============================================================


async def _blacklist_add(event: MessageEvent, tokens: List[ArgToken], _scope: str):
    if not tokens:
        await perm_cmd.finish("用法: 权限 黑名单 添加 <QQ号> [原因]")
    qq = _try_parse_qq(tokens[0])
    if qq is None:
        await perm_cmd.finish("请提供有效的 QQ 号")
    reason = " ".join(t.value for t in tokens[1:]) if len(tokens) > 1 else ""
    try:
        async with async_session_factory() as session:
            existing = (await session.execute(
                select(UserBlacklist.id).where(UserBlacklist.user_id == qq).limit(1)
            )).first()
            if existing:
                await perm_cmd.finish(f"QQ {qq} 已在黑名单中")
            session.add(UserBlacklist(user_id=qq, reason=reason, created_by=event.user_id))
            await session.commit()
        _invalidate_related_cache(user_id=qq)
        await perm_cmd.finish(f"已将 QQ {qq} 加入黑名单" + (f"（原因: {reason}）" if reason else ""))
    except FinishedException:
        pass
    except Exception as e:
        await perm_cmd.finish(f"操作失败: {e}")


async def _blacklist_remove(event: MessageEvent, tokens: List[ArgToken], _scope: str):
    if not tokens:
        await perm_cmd.finish("用法: 权限 黑名单 移除 <QQ号>")
    qq = _try_parse_qq(tokens[0])
    if qq is None:
        await perm_cmd.finish("请提供有效的 QQ 号")
    async with async_session_factory() as session:
        result = await session.execute(
            sa_delete(UserBlacklist).where(UserBlacklist.user_id == qq)
        )
        await session.commit()
        if result.rowcount == 0:
            await perm_cmd.finish(f"QQ {qq} 不在黑名单中")
    _invalidate_related_cache(user_id=qq)
    await perm_cmd.finish(f"已将 QQ {qq} 从黑名单移除")


async def _blacklist_list(event: MessageEvent, _scope: str):
    async with async_session_factory() as session:
        result = await session.execute(
            select(UserBlacklist).order_by(UserBlacklist.created_at.desc())
        )
        rows = result.scalars().all()
    if not rows:
        await perm_cmd.finish("黑名单为空")
    lines = [f"黑名单（共 {len(rows)} 人）："]
    for r in rows:
        lines.append(f"- QQ {r.user_id}" + (f"（{r.reason}）" if r.reason else ""))
    await perm_cmd.finish("\n".join(lines))


# ============================================================
# 白名单操作
# ============================================================


async def _whitelist_add(event: MessageEvent, tokens: List[ArgToken], scope: str):
    if not tokens:
        await perm_cmd.finish(f"用法: 权限 白名单 {scope} 添加 <{'QQ号' if scope == '用户' else '群号'}> [原因]")
    qq = _try_parse_qq(tokens[0])
    if qq is None:
        await perm_cmd.finish("请提供有效的 QQ/群号")
    reason = " ".join(t.value for t in tokens[1:]) if len(tokens) > 1 else ""
    model_cls = UserWhitelist if scope == "用户" else GroupWhitelist
    id_col = UserWhitelist.user_id if scope == "用户" else GroupWhitelist.group_id
    id_label = "QQ" if scope == "用户" else "群"
    try:
        async with async_session_factory() as session:
            existing = (await session.execute(
                select(model_cls.id).where(id_col == qq).limit(1)
            )).first()
            if existing:
                await perm_cmd.finish(f"{id_label} {qq} 已在白名单中")
            kwargs = {("user_id" if scope == "用户" else "group_id"): qq,
                       "reason": reason, "created_by": event.user_id}
            session.add(model_cls(**kwargs))
            await session.commit()
        if scope == "用户":
            _invalidate_related_cache(user_id=qq)
        else:
            _invalidate_related_cache(group_id=qq)
        await perm_cmd.finish(f"已将 {id_label} {qq} 加入白名单" + (f"（原因: {reason}）" if reason else ""))
    except FinishedException:
        pass
    except Exception as e:
        await perm_cmd.finish(f"操作失败: {e}")


async def _whitelist_remove(event: MessageEvent, tokens: List[ArgToken], scope: str):
    if not tokens:
        await perm_cmd.finish(f"用法: 权限 白名单 {scope} 移除 <{'QQ号' if scope == '用户' else '群号'}>")
    qq = _try_parse_qq(tokens[0])
    if qq is None:
        await perm_cmd.finish("请提供有效的 QQ/群号")
    model_cls = UserWhitelist if scope == "用户" else GroupWhitelist
    id_col = UserWhitelist.user_id if scope == "用户" else GroupWhitelist.group_id
    id_label = "QQ" if scope == "用户" else "群"
    async with async_session_factory() as session:
        result = await session.execute(
            sa_delete(model_cls).where(id_col == qq)
        )
        await session.commit()
        if result.rowcount == 0:
            await perm_cmd.finish(f"{id_label} {qq} 不在白名单中")
    if scope == "用户":
        _invalidate_related_cache(user_id=qq)
    else:
        _invalidate_related_cache(group_id=qq)
    await perm_cmd.finish(f"已将 {id_label} {qq} 从白名单移除")


async def _whitelist_list(event: MessageEvent, scope: str):
    model_cls = UserWhitelist if scope == "用户" else GroupWhitelist
    id_col = UserWhitelist.user_id if scope == "用户" else GroupWhitelist.group_id
    label = "QQ" if scope == "用户" else "群号"
    async with async_session_factory() as session:
        result = await session.execute(
            select(model_cls).order_by(model_cls.created_at.desc())
        )
        rows = result.scalars().all()
    if not rows:
        await perm_cmd.finish(f"{scope}白名单为空")
    lines = [f"{scope}白名单（共 {len(rows)} 条）："]
    for r in rows:
        rid = r.user_id if scope == "用户" else r.group_id
        lines.append(f"- {label} {rid}" + (f"（{r.reason}）" if r.reason else ""))
    await perm_cmd.finish("\n".join(lines))


# ============================================================
# 权限组操作
# ============================================================


async def _perm_group_create(event: MessageEvent, tokens: List[ArgToken]):
    if not tokens:
        await perm_cmd.finish("用法: 权限 权限组 创建 <名称> [展示名] [描述]")
    name = tokens[0].value
    display_name = tokens[1].value if len(tokens) >= 2 else ""
    description = " ".join(t.value for t in tokens[2:]) if len(tokens) >= 3 else ""
    try:
        async with async_session_factory() as session:
            existing = (await session.execute(
                select(PermissionGroup.id).where(PermissionGroup.name == name).limit(1)
            )).first()
            if existing:
                await perm_cmd.finish(f"权限组 {name} 已存在")
            session.add(PermissionGroup(
                name=name,
                display_name=display_name,
                description=description,
                created_by=event.user_id,
            ))
            await session.commit()
        _invalidate_related_cache()
        await perm_cmd.finish(f"权限组 {name} 创建成功")
    except FinishedException:
        pass
    except Exception as e:
        await perm_cmd.finish(f"操作失败: {e}")


async def _perm_group_delete(event: MessageEvent, tokens: List[ArgToken]):
    if not tokens:
        await perm_cmd.finish("用法: 权限 权限组 删除 <名称>")
    name = tokens[0].value
    async with async_session_factory() as session:
        result = await session.execute(
            sa_delete(PermissionGroup).where(PermissionGroup.name == name)
        )
        await session.commit()
        if result.rowcount == 0:
            await perm_cmd.finish(f"权限组 {name} 不存在")
    _invalidate_related_cache()
    await perm_cmd.finish(f"权限组 {name} 已删除")


async def _perm_group_list(event: MessageEvent):
    async with async_session_factory() as session:
        result = await session.execute(
            select(PermissionGroup).order_by(PermissionGroup.name)
        )
        groups = result.scalars().all()
    if not groups:
        await perm_cmd.finish("暂无权限组")
    lines = [f"权限组列表（共 {len(groups)} 个）："]
    for g in groups:
        display = g.display_name or g.name
        alias = f"（{display}）" if display != g.name else ""
        desc = f" - {g.description}" if g.description else ""
        lines.append(f"- {g.name}{alias}{desc}")
    await perm_cmd.finish("\n".join(lines))


async def _perm_group_detail(event: MessageEvent, tokens: List[ArgToken]):
    if not tokens:
        await perm_cmd.finish("用法: 权限 权限组 详情 <名称>")
    name = tokens[0].value
    async with async_session_factory() as session:
        result = await session.execute(
            select(PermissionGroup)
            .where(PermissionGroup.name == name)
            .options(
                selectinload(PermissionGroup.members),
                selectinload(PermissionGroup.permissions),
            )
        )
        group = result.scalars().first()
    if not group:
        await perm_cmd.finish(f"权限组 {name} 不存在")
    lines = [f"权限组: {group.name}"]
    if group.display_name:
        lines.append(f"展示名: {group.display_name}")
    if group.description:
        lines.append(f"描述: {group.description}")
    # 成员
    members = sorted(group.members, key=lambda m: m.created_at)
    lines.append(f"成员（{len(members)} 人）:")
    for m in members:
        lines.append(f"  - QQ {m.user_id}")
    # 权限点
    perms = group.permissions
    lines.append(f"权限点（{len(perms)} 个）:")
    for p in perms:
        lines.append(f"  - {p.perm_key}")
    await perm_cmd.finish("\n".join(lines))


async def _perm_group_add_member(event: MessageEvent, tokens: List[ArgToken]):
    if len(tokens) < 2:
        await perm_cmd.finish("用法: 权限 权限组 添加成员 <名称> <QQ> [QQ...]")
    group_name = tokens[0].value
    async with async_session_factory() as session:
        # 验证权限组存在
        pg_result = await session.execute(
            select(PermissionGroup.id).where(PermissionGroup.name == group_name).limit(1)
        )
        pg_row = pg_result.first()
        if not pg_row:
            await perm_cmd.finish(f"权限组 {group_name} 不存在")
        pg_id = pg_row[0]

        added, skipped = [], []
        for token in tokens[1:]:
            qq = _try_parse_qq(token)
            if qq is None:
                continue
            existing = (await session.execute(
                select(PermissionGroupMember.id).where(
                    PermissionGroupMember.group_id == pg_id,
                    PermissionGroupMember.user_id == qq,
                ).limit(1)
            )).first()
            if existing:
                skipped.append(str(qq))
            else:
                session.add(PermissionGroupMember(group_id=pg_id, user_id=qq))
                added.append(str(qq))

        if added:
            await session.commit()

    _invalidate_related_cache()
    lines = [f"权限组 {group_name} 添加成员结果："]
    if added:
        lines.append(f"√ 已添加: {', '.join(added)}")
    if skipped:
        lines.append(f"⚠ 已在组中: {', '.join(skipped)}")
    if not added and not skipped:
        lines.append("未找到有效的 QQ 号")
    await perm_cmd.finish("\n".join(lines))


async def _perm_group_remove_member(event: MessageEvent, tokens: List[ArgToken]):
    if len(tokens) < 2:
        await perm_cmd.finish("用法: 权限 权限组 移除成员 <名称> <QQ>")
    group_name = tokens[0].value
    qq = _try_parse_qq(tokens[1])
    if qq is None:
        await perm_cmd.finish("请提供有效的 QQ 号")

    async with async_session_factory() as session:
        pg_result = await session.execute(
            select(PermissionGroup.id).where(PermissionGroup.name == group_name).limit(1)
        )
        pg_row = pg_result.first()
        if not pg_row:
            await perm_cmd.finish(f"权限组 {group_name} 不存在")
        pg_id = pg_row[0]

        result = await session.execute(
            sa_delete(PermissionGroupMember).where(
                PermissionGroupMember.group_id == pg_id,
                PermissionGroupMember.user_id == qq,
            )
        )
        await session.commit()
        if result.rowcount == 0:
            await perm_cmd.finish(f"QQ {qq} 不在权限组 {group_name} 中")

    _invalidate_related_cache(user_id=qq)
    await perm_cmd.finish(f"已将 QQ {qq} 从权限组 {group_name} 移除")


async def _perm_group_add_perm(event: MessageEvent, tokens: List[ArgToken]):
    if len(tokens) < 2:
        await perm_cmd.finish("用法: 权限 权限组 添加权限 <名称> <perm_key> [perm_key...]")
    group_name = tokens[0].value
    async with async_session_factory() as session:
        pg_result = await session.execute(
            select(PermissionGroup.id).where(PermissionGroup.name == group_name).limit(1)
        )
        pg_row = pg_result.first()
        if not pg_row:
            await perm_cmd.finish(f"权限组 {group_name} 不存在")
        pg_id = pg_row[0]

        added, skipped = [], []
        for token in tokens[1:]:
            perm_key = token.value
            existing = (await session.execute(
                select(PermissionGroupPerm.id).where(
                    PermissionGroupPerm.group_id == pg_id,
                    PermissionGroupPerm.perm_key == perm_key,
                ).limit(1)
            )).first()
            if existing:
                skipped.append(perm_key)
            else:
                session.add(PermissionGroupPerm(group_id=pg_id, perm_key=perm_key))
                added.append(perm_key)

        if added:
            await session.commit()

    _invalidate_related_cache()
    lines = [f"权限组 {group_name} 添加权限结果："]
    if added:
        lines.append(f"√ 已添加: {', '.join(added)}")
    if skipped:
        lines.append(f"⚠ 已有: {', '.join(skipped)}")
    await perm_cmd.finish("\n".join(lines))


async def _perm_group_remove_perm(event: MessageEvent, tokens: List[ArgToken]):
    if len(tokens) < 2:
        await perm_cmd.finish("用法: 权限 权限组 移除权限 <名称> <perm_key>")
    group_name = tokens[0].value
    perm_key = tokens[1].value

    async with async_session_factory() as session:
        pg_result = await session.execute(
            select(PermissionGroup.id).where(PermissionGroup.name == group_name).limit(1)
        )
        pg_row = pg_result.first()
        if not pg_row:
            await perm_cmd.finish(f"权限组 {group_name} 不存在")
        pg_id = pg_row[0]

        result = await session.execute(
            sa_delete(PermissionGroupPerm).where(
                PermissionGroupPerm.group_id == pg_id,
                PermissionGroupPerm.perm_key == perm_key,
            )
        )
        await session.commit()
        if result.rowcount == 0:
            await perm_cmd.finish(f"权限点 {perm_key} 不在权限组 {group_name} 中")

    _invalidate_related_cache()
    await perm_cmd.finish(f"已将权限点 {perm_key} 从权限组 {group_name} 移除")


async def _perm_group_batch_add_group(event: MessageEvent, tokens: List[ArgToken]):
    """将指定群内所有成员批量加入权限组"""
    if len(tokens) < 2:
        await perm_cmd.finish("用法: 权限 权限组 批量加群 <名称> <群号>")
    group_name = tokens[0].value
    qq_group_id = _try_parse_qq(tokens[1])
    if qq_group_id is None:
        await perm_cmd.finish("请提供有效的群号")
    # 注意：此命令在群聊中使用时才能获取群成员列表，这里仅做绑定
    # 实际"将群内所有成员加入权限组"通过 群绑定 机制实现（见 _binding_add）
    # 此处提供显式的批量加群命令作为快捷方式
    await perm_cmd.finish(
        f"提示：要将群 {qq_group_id} 的所有成员赋予权限组 {group_name} 的权限，"
        f"请使用:\n权限 绑定 群 {qq_group_id} {group_name}\n"
        f"绑定后群内所有用户将自动享有该权限组的全部权限。"
    )


# ============================================================
# 群绑定操作
# ============================================================


async def _binding_add(event: MessageEvent, tokens: List[ArgToken]):
    if len(tokens) < 2:
        await perm_cmd.finish("用法: 权限 绑定 群 <群号> <权限组名>")
    qq = _try_parse_qq(tokens[0])
    if qq is None:
        await perm_cmd.finish("请提供有效的群号")
    pg_name = tokens[1].value

    try:
        async with async_session_factory() as session:
            pg_result = await session.execute(
                select(PermissionGroup.id).where(PermissionGroup.name == pg_name).limit(1)
            )
            pg_row = pg_result.first()
            if not pg_row:
                await perm_cmd.finish(f"权限组 {pg_name} 不存在")
            pg_id = pg_row[0]

            existing = (await session.execute(
                select(GroupPermBinding.id).where(
                    GroupPermBinding.qq_group_id == qq,
                    GroupPermBinding.permission_group_id == pg_id,
                ).limit(1)
            )).first()
            if existing:
                await perm_cmd.finish(f"群 {qq} 已绑定权限组 {pg_name}")

            session.add(GroupPermBinding(qq_group_id=qq, permission_group_id=pg_id))
            await session.commit()
        _invalidate_related_cache(group_id=qq)
        await perm_cmd.finish(f"群 {qq} 已绑定权限组 {pg_name}")
    except FinishedException:
        pass
    except Exception as e:
        await perm_cmd.finish(f"操作失败: {e}")


async def _binding_remove(event: MessageEvent, tokens: List[ArgToken]):
    if not tokens:
        await perm_cmd.finish("用法: 权限 绑定 解除 <群号>")
    qq = _try_parse_qq(tokens[0])
    if qq is None:
        await perm_cmd.finish("请提供有效的群号")

    async with async_session_factory() as session:
        result = await session.execute(
            sa_delete(GroupPermBinding).where(GroupPermBinding.qq_group_id == qq)
        )
        await session.commit()
        if result.rowcount == 0:
            await perm_cmd.finish(f"群 {qq} 没有绑定任何权限组")
    _invalidate_related_cache(group_id=qq)
    await perm_cmd.finish(f"已解除群 {qq} 的所有权限组绑定（共 {result.rowcount} 条）")


async def _binding_list(event: MessageEvent, tokens: List[ArgToken]):
    qq_filter = None
    if tokens:
        qq_filter = _try_parse_qq(tokens[0])

    async with async_session_factory() as session:
        if qq_filter:
            result = await session.execute(
                select(GroupPermBinding).where(GroupPermBinding.qq_group_id == qq_filter)
            )
        else:
            result = await session.execute(
                select(GroupPermBinding).order_by(GroupPermBinding.qq_group_id)
            )
        bindings = result.scalars().all()

    if not bindings:
        await perm_cmd.finish("暂无群绑定记录")
    # 按群号分组
    groups_map: dict[int, list] = {}
    for b in bindings:
        groups_map.setdefault(b.qq_group_id, []).append(b)

    lines = ["群绑定列表："]
    for qq_gid, blist in sorted(groups_map.items()):
        # 加载权限组名
        async with async_session_factory() as session:
            pg_ids = [b.permission_group_id for b in blist]
            pg_result = await session.execute(
                select(PermissionGroup.id, PermissionGroup.name).where(
                    PermissionGroup.id.in_(pg_ids)
                )
            )
            pg_names = {row[0]: row[1] for row in pg_result.all()}
        names = [pg_names.get(b.permission_group_id, f"ID:{b.permission_group_id}") for b in blist]
        lines.append(f"- 群 {qq_gid} → {', '.join(names)}")
    await perm_cmd.finish("\n".join(lines))


# ============================================================
# 权限点列表
# ============================================================


async def _list_permission_points(event: MessageEvent, tokens: List[ArgToken]):
    plugin_filter = tokens[0].value if tokens else None
    async with async_session_factory() as session:
        if plugin_filter:
            result = await session.execute(
                select(PermissionPoint)
                .where(PermissionPoint.plugin_name == plugin_filter)
                .order_by(PermissionPoint.plugin_name, PermissionPoint.perm_key)
            )
        else:
            result = await session.execute(
                select(PermissionPoint).order_by(PermissionPoint.plugin_name, PermissionPoint.perm_key)
            )
        points = result.scalars().all()

    if not points:
        msg = f"插件 {plugin_filter} 未注册任何权限点" if plugin_filter else "暂无已注册的权限点"
        await perm_cmd.finish(msg)

    # 按插件分组
    by_plugin: dict[str, list] = {}
    for p in points:
        by_plugin.setdefault(p.plugin_name or "(未分类)", []).append(p)

    lines = ["已注册的权限点："]
    for pname, plist in sorted(by_plugin.items()):
        lines.append(f"━━━ {pname} ━━━")
        for p in plist:
            lines.append(f"  {p.perm_key} — {p.name}")
    await perm_cmd.finish("\n".join(lines))


# ============================================================
# 查看用户权限
# ============================================================


async def _view_user_permissions(event: MessageEvent, tokens: List[ArgToken]):
    if not tokens:
        await perm_cmd.finish("用法: 权限 查看 <QQ号>")
    qq = _try_parse_qq(tokens[0])
    if qq is None:
        await perm_cmd.finish("请提供有效的 QQ 号")

    lines = [f"QQ {qq} 的权限状态："]

    # 超级管理员
    if is_superuser(qq):
        lines.append("  ✩ 超级管理员（不受任何限制）")
        await perm_cmd.finish("\n".join(lines))

    async with async_session_factory() as session:
        # 黑名单
        bl = (await session.execute(
            select(UserBlacklist).where(UserBlacklist.user_id == qq).limit(1)
        )).scalars().first()
        if bl:
            lines.append(f"  ⛒ 黑名单中" + (f"（原因: {bl.reason}）" if bl.reason else ""))
            await perm_cmd.finish("\n".join(lines))

        # 白名单
        wl = (await session.execute(
            select(UserWhitelist).where(UserWhitelist.user_id == qq).limit(1)
        )).scalars().first()
        if wl:
            lines.append("  √ 用户白名单（完全放行）")

        # 权限组
        pg_result = await session.execute(
            select(PermissionGroupMember, PermissionGroup).join(
                PermissionGroup, PermissionGroupMember.group_id == PermissionGroup.id
            ).where(PermissionGroupMember.user_id == qq)
        )
        memberships = pg_result.all()
        if memberships:
            lines.append("  所属权限组：")
            for member, pg in memberships:
                perms_result = await session.execute(
                    select(PermissionGroupPerm.perm_key).where(
                        PermissionGroupPerm.group_id == pg.id
                    )
                )
                perm_keys = [row[0] for row in perms_result.all()]
                lines.append(f"    - {pg.name}: {', '.join(perm_keys) if perm_keys else '（无权限点）'}")
        else:
            lines.append("  ⚠ 无任何权限（默认拒绝）")

    await perm_cmd.finish("\n".join(lines))

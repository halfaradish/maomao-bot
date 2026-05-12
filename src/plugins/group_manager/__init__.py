from __future__ import annotations

import importlib
from dataclasses import dataclass
from typing import List, Optional

from asgiref.sync import sync_to_async
from django.db.models import Count
from nonebot import get_driver, get_plugin_config, on_command
from nonebot.adapters.onebot.v11 import Bot, Message, MessageEvent
from nonebot.params import CommandArg
from nonebot.plugin import PluginMetadata

from ...common.django_crud import init_django_if_needed

try:  # 优先使用正确的 app label，保证 Django 注册
    botdb_models = importlib.import_module("botdb.models")
except ModuleNotFoundError:  # 在静态检查或路径未注入时的回退（避免运行失败）
    botdb_models = importlib.import_module("src.django_project.botdb.models")

Group = botdb_models.Group
GroupMember = botdb_models.GroupMember
from .config import Config
from src.common.model.model import PluginGroupEnum, PluginBadgeColor

__plugin_meta__ = PluginMetadata(
    name="分组管理",
    description="基于数据库的分组管理插件",
    usage="group ls —— 查看所有分组\ngroup create 组名 [展示名] [描述] —— 创建分组\ngroup add QQ/@用户 组名 [昵称] —— 添加成员\ngroup show 组名 —— 查看成员\ngroup rm 组名 —— 删除分组\ngroup rm QQ/@用户 [组名] —— 删除成员",
    config=Config,
    supported_adapters={"~onebot.v11"},
    extra={
        "group": PluginGroupEnum.GROUP_MANAGE.value,
        "badge_color": PluginBadgeColor.GREEN.value
    }
)


config = get_plugin_config(Config)
driver = get_driver()

init_django_if_needed()


class PermissionError(Exception):
    pass


@dataclass
class ArgToken:
    kind: str  # text / at
    value: str


def _tokenize_arguments(message: Message) -> List[ArgToken]:
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


async def _ensure_superuser(event: MessageEvent) -> None:
    if str(event.user_id) not in driver.config.superusers:
        raise PermissionError("您没有权限使用该命令")


@sync_to_async
def _list_all_groups():
    groups = (
        Group.objects.annotate(member_count=Count("members"))
        .order_by("name")
        .values("name", "display_name", "description", "member_count")
    )
    return list(groups)


@sync_to_async
def _create_group_record(name: str, display_name: str = "", description: str = ""):
    if Group.objects.filter(name=name).exists():
        return False
    Group.objects.create(
        name=name,
        display_name=display_name or "",
        description=description or "",
    )
    return True


@sync_to_async
def _get_group_detail(name: str):
    group = Group.objects.filter(name=name).first()
    if not group:
        return None
    members = list(
        group.members.order_by("added_at").values("qq_id", "qq_nickname", "added_at")
    )
    return {
        "group": group,
        "members": members,
    }


@sync_to_async
def _add_member(group_name: str, qq_id: int, nickname: str = ""):
    group = Group.objects.filter(name=group_name).first()
    if not group:
        return False, "分组不存在"
    member, created = GroupMember.objects.get_or_create(
        group=group,
        qq_id=qq_id,
        defaults={"qq_nickname": nickname},
    )
    if created:
        return True, "成员已加入分组"
    if nickname and nickname != member.qq_nickname:
        member.qq_nickname = nickname
        member.save(update_fields=["qq_nickname"])
        return True, "成员已存在，昵称已更新"
    return False, "成员已在该分组中"


@sync_to_async
def _delete_group(name: str) -> int:
    deleted, _ = Group.objects.filter(name=name).delete()
    return deleted


@sync_to_async
def _remove_member(qq_id: int, group_name: Optional[str] = None) -> int:
    qs = GroupMember.objects.filter(qq_id=qq_id)
    if group_name:
        qs = qs.filter(group__name=group_name)
    deleted, _ = qs.delete()
    return deleted


def _build_help_text() -> str:
    return (
        "group 命令可用操作：\n"
        "1. group ls 查看所有分组\n"
        "2. group create 组名 [展示名] [描述]\n"
        "3. group add QQ/@用户 组名 [昵称]\n"
        "4. group show 组名 查看成员\n"
        "5. group rm 组名 删除分组\n"
        "6. group rm QQ/@用户 [组名] 删除成员（不带组名删除其所有分组）"
    )


def _extract_user_id(tokens: List[ArgToken]) -> (Optional[int], Optional[int]):
    for idx, token in enumerate(tokens):
        if token.kind == "at" and token.value.isdigit():
            return int(token.value), idx
        if token.kind == "text":
            text = token.value.lstrip("@")
            if text.isdigit():
                return int(text), idx
    return None, None


def _try_parse_user_token(token: ArgToken) -> Optional[int]:
    if token.kind == "at" and token.value.isdigit():
        return int(token.value)
    if token.kind == "text":
        text = token.value.lstrip("@")
        if text.isdigit():
            return int(text)
    return None


def _parse_add_arguments(tokens: List[ArgToken]):
    """
    将参数拆分为 [(user_id, nickname), ...], group_name
    约定：最后一个 token 为分组名；其余按照 @用户 + 可选昵称 的顺序解析
    """
    if not tokens or tokens[-1].kind != "text":
        raise ValueError("请在指令末尾提供分组名称")
    group_name = tokens[-1].value
    member_tokens = tokens[:-1]
    specs = []
    idx = 0
    while idx < len(member_tokens):
        token = member_tokens[idx]
        user_id = _try_parse_user_token(token)
        if user_id is None:
            idx += 1
            continue
        idx += 1
        nickname_parts: List[str] = []
        while idx < len(member_tokens):
            next_token = member_tokens[idx]
            if _try_parse_user_token(next_token) is not None:
                break
            nickname_parts.append(next_token.value)
            idx += 1
        nickname = " ".join(part.strip() for part in nickname_parts).strip()
        specs.append((user_id, nickname))
    if not specs:
        raise ValueError("请提供至少一个 QQ 号或 @ 成员")
    return specs, group_name


async def _resolve_member_name(bot: Bot, event: MessageEvent, target_id: int) -> str:
    """优先使用命令所在群的群名片；若没有则使用 QQ 昵称"""
    group_id = getattr(event, "group_id", None)
    if group_id:
        try:
            info = await bot.get_group_member_info(
                group_id=int(group_id),
                user_id=int(target_id),
                no_cache=True,
            )
            card = info.get("card", "").strip()
            nickname = info.get("nickname", "").strip()
            if card or nickname:
                return card or nickname
        except Exception:
            pass
    try:
        info = await bot.get_stranger_info(user_id=int(target_id), no_cache=True)
        nickname = info.get("nickname", "").strip()
        return nickname
    except Exception:
        return ""


group_cmd = on_command(
    config.command,
    priority=config.priority,
    block=config.block,
)


@group_cmd.handle()
async def handle_group_command(
    bot: Bot,
    event: MessageEvent,
    args: Message = CommandArg(),
):
    try:
        await _ensure_superuser(event)
    except PermissionError as exc:
        await group_cmd.finish(str(exc))

    tokens = _tokenize_arguments(args)
    if not tokens:
        await group_cmd.finish(_build_help_text())

    subcommand = tokens[0].value.lower()
    rest = tokens[1:]

    if subcommand == "ls":
        groups = await _list_all_groups()
        if not groups:
            await group_cmd.finish("当前没有任何分组，请使用 group create 创建。")
        lines = []
        for g in groups:
            display = g["display_name"] or g["name"]
            desc = f" - {g['description']}" if g["description"] else ""
            alias = f"（别名：{display}）" if display != g["name"] else ""
            lines.append(f"{g['name']}{alias} 共 {g['member_count']} 人{desc}")
        await group_cmd.finish("\n".join(lines))

    if subcommand == "create":
        if not rest:
            await group_cmd.finish("用法：group create 组名 [展示名] [描述]")
        name = rest[0].value
        display_name = rest[1].value if len(rest) >= 2 else ""
        description = " ".join(token.value for token in rest[2:]) if len(rest) >= 3 else ""
        ok = await _create_group_record(name, display_name, description)
        if not ok:
            await group_cmd.finish(f"分组 {name} 已存在。")
        await group_cmd.finish(f"分组 {name} 创建成功。")

    if subcommand == "show":
        if not rest:
            await group_cmd.finish("用法：group show 组名")
        group_name = rest[0].value
        detail = await _get_group_detail(group_name)
        if not detail:
            await group_cmd.finish(f"未找到分组 {group_name}")
        members = detail["members"]
        if not members:
            await group_cmd.finish(f"{group_name} 暂无成员。")
        total = len(members)
        preview = members[: config.max_members_preview]
        lines = [
            f"{group_name} 共 {total} 人，展示前 {len(preview)} 人：",
        ]
        for m in preview:
            show_name = m["qq_nickname"] or str(m["qq_id"])
            lines.append(f"- {show_name}（{m['qq_id']}）")
        if total > len(preview):
            lines.append(f"... 其余 {total - len(preview)} 人已省略")
        await group_cmd.finish("\n".join(lines))

    if subcommand == "add":
        if not rest:
            await group_cmd.finish("用法：group add QQ/@用户 组名 [昵称]")
        try:
            member_specs, group_name = _parse_add_arguments(rest)
        except ValueError as exc:
            await group_cmd.finish(str(exc))
        lines = [f"分组 {group_name} 添加结果："]
        for user_id, nickname in member_specs:
            resolved_name = nickname or await _resolve_member_name(bot, event, user_id)
            ok, msg = await _add_member(group_name, user_id, resolved_name)
            prefix = "✅" if ok else "⚠️"
            display_name = resolved_name or "(无昵称)"
            lines.append(f"{prefix} {display_name}（{user_id}）: {msg}")
        await group_cmd.finish("\n".join(lines))

    if subcommand == "rm":
        if not rest:
            await group_cmd.finish("用法：group rm 组名 或 group rm QQ/@用户 [组名]")
        first = rest[0]
        if first.kind == "at" or first.value.lstrip("@").isdigit():
            user_id = first.value if first.kind == "at" else first.value.lstrip("@")
            if not user_id.isdigit():
                await group_cmd.finish("请提供有效的 QQ 号。")
            group_name = rest[1].value if len(rest) >= 2 and rest[1].kind == "text" else None
            deleted = await _remove_member(int(user_id), group_name)
            if deleted == 0:
                target = f"{group_name} 中 " if group_name else ""
                await group_cmd.finish(f"未找到{target}QQ {user_id}。")
            scope = f"分组 {group_name}" if group_name else "所有分组"
            await group_cmd.finish(f"已从{scope}移除 QQ {user_id}（{deleted} 条记录）。")
        else:
            group_name = first.value
            deleted = await _delete_group(group_name)
            if deleted == 0:
                await group_cmd.finish(f"分组 {group_name} 不存在。")
            await group_cmd.finish(f"分组 {group_name} 已删除。")

    await group_cmd.finish(_build_help_text())


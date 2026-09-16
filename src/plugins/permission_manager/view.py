"""只读查询子命令：注册点列表与用户权限状态。

注意 `_view_user_permissions` 只查 `PermissionGroupMember` 直接成员关系，不查
`GroupPermBinding`——通过群绑定获得权限的用户会被显示为「无任何权限」。
"""
from typing import List

from nonebot.adapters.onebot.v11 import MessageEvent
from sqlalchemy import select

from src.common.database import async_session_factory
from src.common.permission.models import (
    PermissionPoint,
    UserBlacklist,
    UserWhitelist,
    PermissionGroup,
    PermissionGroupMember,
    PermissionGroupPerm,
)
from src.common.permission.supervisor import is_superuser

from .helpers import ArgToken, _try_parse_qq
from .runtime import perm_cmd


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

"""权限组子命令：CRUD、成员增删、权限点增删。"""
from typing import List

from nonebot import logger
from nonebot.adapters.onebot.v11 import MessageEvent
from nonebot.exception import FinishedException
from sqlalchemy import select, delete as sa_delete
from sqlalchemy.orm import selectinload

from src.common.arg_parser import ArgToken, try_parse_qq
from src.common.database import async_session_factory
from src.common.permission.models import (
    PermissionGroup,
    PermissionGroupMember,
    PermissionGroupPerm,
)

from .guard import _invalidate_related_cache
from .runtime import perm_cmd


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
        logger.info(f"用户 {event.user_id} 创建权限组 {name}")
        await perm_cmd.finish(f"权限组 {name} 创建成功")
    except FinishedException:
        pass
    except Exception as e:
        logger.error(f"权限组创建失败: {e}", exc_info=True)
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
            logger.warning(f"用户 {event.user_id} 尝试删除权限组 {name}，但该权限组不存在")
            await perm_cmd.finish(f"权限组 {name} 不存在")
    _invalidate_related_cache()
    logger.info(f"用户 {event.user_id} 已删除权限组 {name}")
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
            qq = try_parse_qq(token)
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
    logger.info(f"用户 {event.user_id} 向权限组 {group_name} 添加成员: {', '.join(added) if added else '无'}" + (f"，跳过（已在组内）: {', '.join(skipped)}" if skipped else ""))
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
    qq = try_parse_qq(tokens[1])
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
            logger.warning(f"用户 {event.user_id} 尝试从权限组 {group_name} 移除 QQ {qq}，但该用户不在组内")
            await perm_cmd.finish(f"QQ {qq} 不在权限组 {group_name} 中")

    _invalidate_related_cache(user_id=qq)
    logger.info(f"用户 {event.user_id} 已将 QQ {qq} 从权限组 {group_name} 移除")
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
    logger.info(f"用户 {event.user_id} 为权限组 {group_name} 添加权限点: {', '.join(added) if added else '无'}" + (f"，跳过（已有）: {', '.join(skipped)}" if skipped else ""))
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
            logger.warning(f"用户 {event.user_id} 尝试从权限组 {group_name} 移除权限点 {perm_key}，但该权限点不在组内")
            await perm_cmd.finish(f"权限点 {perm_key} 不在权限组 {group_name} 中")

    _invalidate_related_cache()
    logger.info(f"用户 {event.user_id} 已将权限点 {perm_key} 从权限组 {group_name} 移除")
    await perm_cmd.finish(f"已将权限点 {perm_key} 从权限组 {group_name} 移除")


async def _perm_group_batch_add_group(event: MessageEvent, tokens: List[ArgToken]):
    """将指定群内所有成员批量加入权限组"""
    if len(tokens) < 2:
        await perm_cmd.finish("用法: 权限 权限组 批量加群 <名称> <群号>")
    group_name = tokens[0].value
    qq_group_id = try_parse_qq(tokens[1])
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

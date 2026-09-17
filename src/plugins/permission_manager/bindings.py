"""群绑定子命令：把 QQ 群绑定到权限组。"""
from typing import List

from nonebot import logger
from nonebot.adapters.onebot.v11 import MessageEvent
from nonebot.exception import FinishedException
from sqlalchemy import select, delete as sa_delete

from src.common.arg_parser import ArgToken, try_parse_qq
from src.common.database import get_session
from src.common.permission.models import PermissionGroup, GroupPermBinding

from .guard import _invalidate_related_cache
from .runtime import perm_cmd


async def _binding_add(event: MessageEvent, tokens: List[ArgToken]):
    if len(tokens) < 2:
        await perm_cmd.finish("用法: 权限 绑定 群 <群号> <权限组名>")
    qq = try_parse_qq(tokens[0])
    if qq is None:
        await perm_cmd.finish("请提供有效的群号")
    pg_name = tokens[1].value

    try:
        # finish() 在块内会抛 FinishedException → get_session 回滚并重抛，
        # 所以两个提前返回分支都只记标志，提示一律放到块外。
        not_found = already = False
        async with get_session() as session:
            pg_result = await session.execute(
                select(PermissionGroup.id).where(PermissionGroup.name == pg_name).limit(1)
            )
            pg_row = pg_result.first()
            if not pg_row:
                not_found = True
            else:
                pg_id = pg_row[0]
                existing = (await session.execute(
                    select(GroupPermBinding.id).where(
                        GroupPermBinding.qq_group_id == qq,
                        GroupPermBinding.permission_group_id == pg_id,
                    ).limit(1)
                )).first()
                if existing:
                    already = True
                else:
                    session.add(GroupPermBinding(qq_group_id=qq, permission_group_id=pg_id))
        if not_found:
            await perm_cmd.finish(f"权限组 {pg_name} 不存在")
        if already:
            await perm_cmd.finish(f"群 {qq} 已绑定权限组 {pg_name}")
        _invalidate_related_cache(group_id=qq)
        logger.info(f"用户 {event.user_id} 将群 {qq} 绑定到权限组 {pg_name}")
        await perm_cmd.finish(f"群 {qq} 已绑定权限组 {pg_name}")
    except FinishedException:
        pass
    except Exception as e:
        logger.error(f"群绑定失败: {e}", exc_info=True)
        await perm_cmd.finish(f"操作失败: {e}")


async def _binding_remove(event: MessageEvent, tokens: List[ArgToken]):
    if not tokens:
        await perm_cmd.finish("用法: 权限 绑定 解除 <群号>")
    qq = try_parse_qq(tokens[0])
    if qq is None:
        await perm_cmd.finish("请提供有效的群号")

    async with get_session() as session:
        result = await session.execute(
            sa_delete(GroupPermBinding).where(GroupPermBinding.qq_group_id == qq)
        )
    if result.rowcount == 0:
        logger.warning(f"用户 {event.user_id} 尝试解除群 {qq} 的绑定，但该群没有绑定记录")
        await perm_cmd.finish(f"群 {qq} 没有绑定任何权限组")
    _invalidate_related_cache(group_id=qq)
    logger.info(f"用户 {event.user_id} 已解除群 {qq} 的 {result.rowcount} 条权限组绑定")
    await perm_cmd.finish(f"已解除群 {qq} 的所有权限组绑定（共 {result.rowcount} 条）")


async def _binding_list(event: MessageEvent, tokens: List[ArgToken]):
    qq_filter = None
    if tokens:
        qq_filter = try_parse_qq(tokens[0])

    async with get_session(commit=False) as session:
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
        async with get_session(commit=False) as session:
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

"""白名单子命令（用户 / 群两个维度共用同一组 handler，靠 scope 分派）。"""
from typing import List

from nonebot import logger
from nonebot.adapters.onebot.v11 import MessageEvent
from nonebot.exception import FinishedException
from sqlalchemy import select, delete as sa_delete

from src.common.arg_parser import ArgToken, try_parse_qq
from src.common.database import get_session
from src.common.permission.models import UserWhitelist, GroupWhitelist

from .guard import _invalidate_related_cache
from .runtime import perm_cmd


async def _whitelist_add(event: MessageEvent, tokens: List[ArgToken], scope: str):
    if not tokens:
        await perm_cmd.finish(f"用法: 权限 白名单 {scope} 添加 <{'QQ号' if scope == '用户' else '群号'}> [原因]")
    qq = try_parse_qq(tokens[0])
    if qq is None:
        await perm_cmd.finish("请提供有效的 QQ/群号")
    reason = " ".join(t.value for t in tokens[1:]) if len(tokens) > 1 else ""
    model_cls = UserWhitelist if scope == "用户" else GroupWhitelist
    id_col = UserWhitelist.user_id if scope == "用户" else GroupWhitelist.group_id
    id_label = "QQ" if scope == "用户" else "群"
    try:
        # finish() 在块内会抛 FinishedException → get_session 回滚并重抛，
        # 所以「已在名单中」只记标志，提示一律放到块外。
        exists = False
        async with get_session() as session:
            existing = (await session.execute(
                select(model_cls.id).where(id_col == qq).limit(1)
            )).first()
            if existing:
                exists = True
            else:
                kwargs = {("user_id" if scope == "用户" else "group_id"): qq,
                           "reason": reason, "created_by": event.user_id}
                session.add(model_cls(**kwargs))
        if exists:
            await perm_cmd.finish(f"{id_label} {qq} 已在白名单中")
        if scope == "用户":
            _invalidate_related_cache(user_id=qq)
        else:
            _invalidate_related_cache(group_id=qq)
        logger.info(f"用户 {event.user_id} 将 {id_label} {qq} 加入{scope}白名单（原因: {reason or '未填写'}）")
        await perm_cmd.finish(f"已将 {id_label} {qq} 加入白名单" + (f"（原因: {reason}）" if reason else ""))
    except FinishedException:
        pass
    except Exception as e:
        logger.error(f"白名单添加失败: {e}", exc_info=True)
        await perm_cmd.finish(f"操作失败: {e}")


async def _whitelist_remove(event: MessageEvent, tokens: List[ArgToken], scope: str):
    if not tokens:
        await perm_cmd.finish(f"用法: 权限 白名单 {scope} 移除 <{'QQ号' if scope == '用户' else '群号'}>")
    qq = try_parse_qq(tokens[0])
    if qq is None:
        await perm_cmd.finish("请提供有效的 QQ/群号")
    model_cls = UserWhitelist if scope == "用户" else GroupWhitelist
    id_col = UserWhitelist.user_id if scope == "用户" else GroupWhitelist.group_id
    id_label = "QQ" if scope == "用户" else "群"
    async with get_session() as session:
        result = await session.execute(
            sa_delete(model_cls).where(id_col == qq)
        )
    if result.rowcount == 0:
        logger.warning(f"用户 {event.user_id} 尝试移除{scope}白名单 {id_label} {qq}，但不在白名单中")
        await perm_cmd.finish(f"{id_label} {qq} 不在白名单中")
    if scope == "用户":
        _invalidate_related_cache(user_id=qq)
    else:
        _invalidate_related_cache(group_id=qq)
    logger.info(f"用户 {event.user_id} 已将 {id_label} {qq} 从{scope}白名单移除")
    await perm_cmd.finish(f"已将 {id_label} {qq} 从白名单移除")


async def _whitelist_list(event: MessageEvent, scope: str):
    model_cls = UserWhitelist if scope == "用户" else GroupWhitelist
    id_col = UserWhitelist.user_id if scope == "用户" else GroupWhitelist.group_id
    label = "QQ" if scope == "用户" else "群号"
    async with get_session(commit=False) as session:
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

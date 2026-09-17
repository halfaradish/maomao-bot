"""黑名单子命令。

当前只支持用户维度：三个 handler 的 `_scope` 形参恒为 "user"，群黑名单尚未
接线（REST API 侧两侧都已支持）。
"""
from typing import List

from nonebot import logger
from nonebot.adapters.onebot.v11 import MessageEvent
from nonebot.exception import FinishedException
from sqlalchemy import select, delete as sa_delete

from src.common.arg_parser import ArgToken, try_parse_qq
from src.common.database import get_session
from src.common.permission.models import UserBlacklist

from .guard import _invalidate_related_cache
from .runtime import perm_cmd


async def _blacklist_add(event: MessageEvent, tokens: List[ArgToken], _scope: str):
    if not tokens:
        await perm_cmd.finish("用法: 权限 黑名单 添加 <QQ号> [原因]")
    qq = try_parse_qq(tokens[0])
    if qq is None:
        await perm_cmd.finish("请提供有效的 QQ 号")
    reason = " ".join(t.value for t in tokens[1:]) if len(tokens) > 1 else ""
    try:
        # finish() 在块内会抛 FinishedException → get_session 回滚并重抛，
        # 所以「已在名单中」只记标志，提示一律放到块外。
        exists = False
        async with get_session() as session:
            existing = (await session.execute(
                select(UserBlacklist.id).where(UserBlacklist.user_id == qq).limit(1)
            )).first()
            if existing:
                exists = True
            else:
                session.add(UserBlacklist(user_id=qq, reason=reason, created_by=event.user_id))
        if exists:
            await perm_cmd.finish(f"QQ {qq} 已在黑名单中")
        _invalidate_related_cache(user_id=qq)
        logger.info(f"用户 {event.user_id} 将 QQ {qq} 加入黑名单（原因: {reason or '未填写'}）")
        await perm_cmd.finish(f"已将 QQ {qq} 加入黑名单" + (f"（原因: {reason}）" if reason else ""))
    except FinishedException:
        pass
    except Exception as e:
        logger.error(f"黑名单添加失败: {e}", exc_info=True)
        await perm_cmd.finish(f"操作失败: {e}")


async def _blacklist_remove(event: MessageEvent, tokens: List[ArgToken], _scope: str):
    if not tokens:
        await perm_cmd.finish("用法: 权限 黑名单 移除 <QQ号>")
    qq = try_parse_qq(tokens[0])
    if qq is None:
        await perm_cmd.finish("请提供有效的 QQ 号")
    async with get_session() as session:
        result = await session.execute(
            sa_delete(UserBlacklist).where(UserBlacklist.user_id == qq)
        )
    if result.rowcount == 0:
        logger.warning(f"用户 {event.user_id} 尝试移除黑名单 QQ {qq}，但该用户不在黑名单中")
        await perm_cmd.finish(f"QQ {qq} 不在黑名单中")
    _invalidate_related_cache(user_id=qq)
    logger.info(f"用户 {event.user_id} 已将 QQ {qq} 从黑名单移除")
    await perm_cmd.finish(f"已将 QQ {qq} 从黑名单移除")


async def _blacklist_list(event: MessageEvent, _scope: str):
    async with get_session(commit=False) as session:
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

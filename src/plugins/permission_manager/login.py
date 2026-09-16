"""`权限 登录` 子命令：生成 Web 面板验证码并完成私聊/本会话的二次确认。

本模块的 `@perm_cmd.got("login_confirm")` 必须在 `dispatch.py` 的
`@perm_cmd.handle()` 之后注册——`got` 的依赖在函数体之前解析，顺序颠倒会让每条
`权限` 命令都变成「是否通过私聊发送验证码？(是/否)」的提问。
"""
import secrets

from nonebot import logger
from nonebot.adapters.onebot.v11 import Bot, MessageEvent, GroupMessageEvent
from nonebot.exception import FinishedException
from nonebot.typing import T_State

from src.common.permission import ADMIN_PERM_KEY, check_permission
from src.common.permission.cache import perm_cache

from .runtime import perm_cmd


async def _handle_login(bot: Bot, event: MessageEvent, state: T_State):
    """处理 `权限 登录` 子命令：生成Web面板临时密码，进入二次确认"""
    if not await check_permission(event, ADMIN_PERM_KEY):
        logger.warning(f"用户 {event.user_id} 尝试获取登录验证码但权限不足")
        await perm_cmd.finish("你没有权限执行此操作")

    temp_pwd = f"{secrets.randbelow(900000) + 100000}"
    qq_number = str(event.user_id)
    logger.info(f"用户 {event.user_id} 已生成Web管理面板登录验证码（5分钟内有效）")
    perm_cache.set(f"webui:temp_pwd:{qq_number}", temp_pwd, ttl=300)
    state["login_ready"] = True
    # 不调用 finish() / pause() — 让 got() handler 接管后续二次确认流程


@perm_cmd.got("login_confirm", prompt="是否通过私聊发送验证码？(是/否)")
async def handle_login_confirm(bot: Bot, event: MessageEvent, state: T_State):
    """处理登录二次确认：是 → 私聊发送，否 → 当前会话发送"""
    if not state.get("login_ready"):
        await perm_cmd.finish()  # 非登录流程，静默结束

    resp = state["login_confirm"].extract_plain_text().strip()
    temp_pwd = perm_cache.get(f"webui:temp_pwd:{event.user_id}")
    if not temp_pwd:
        await perm_cmd.finish("验证码已过期，请重新执行「权限 登录」")

    msg = (
        f"【Web管理面板登录验证码】\n"
        f"验证码: {temp_pwd}\n"
        f"该验证码5分钟内有效\n"
        f"请前往管理面板使用此验证码登录。"
    )

    if resp in ("是", "y", "yes", "Y", "Yes", "YES", "1"):
        try:
            await bot.send_private_msg(user_id=event.user_id, message=msg)
            await perm_cmd.finish("验证码已通过私聊发送，请注意查收")
        except FinishedException:
            pass
        except Exception:
            await perm_cmd.finish("私聊发送失败，请检查是否已添加好友", at_sender=True)
    else:
        if isinstance(event, GroupMessageEvent):
            await perm_cmd.finish(msg, at_sender=True)
        else:
            await perm_cmd.finish(msg)

import os

from nonebot import get_plugin_config, logger, get_driver, on_request
from nonebot.plugin import PluginMetadata
from nonebot.adapters.onebot.v11 import Bot, GroupRequestEvent
from nonebot.rule import Rule
from sqlalchemy import select

from .config import Config
from . import permissions  # noqa: F401 — 注册权限点到权限系统
from .auditor import audit_join_request
from ..auto_manage_group.group_checker import is_group_feature_enabled
from src.common.model.model import PluginGroupEnum, PluginBadgeColor
from src.common.database import async_session_factory
from src.common.permission.models import (
    PermissionGroup,
    PermissionGroupPerm,
)

# ── 插件启停开关 ──
GROUP_SENTINEL_ENABLED = os.getenv("GROUP_SENTINEL_ENABLED", "true").lower() == "true"

if not GROUP_SENTINEL_ENABLED:
    __plugin_meta__ = PluginMetadata(
        name="群哨兵（已禁用）",
        description="入群审核插件（当前已禁用，设置 GROUP_SENTINEL_ENABLED=true 启用）",
        usage="此插件已在环境变量中禁用",
        supported_adapters={"~onebot.v11"},
        extra={
            "group": PluginGroupEnum.GROUP_MANAGE.value,
            "badge_color": PluginBadgeColor.YELLOW.value,
        },
    )
else:
    __plugin_meta__ = PluginMetadata(
        name="群哨兵",
        description="审核用户加群请求，根据入群回答判断是否放行",
        usage="自动运行，通过 perm 绑定 命令配置监控的群聊",
        config=Config,
        supported_adapters={"~onebot.v11"},
        extra={
            "group": PluginGroupEnum.GROUP_MANAGE.value,
            "badge_color": PluginBadgeColor.GREEN.value,
        },
    )

    plugin_config = get_plugin_config(Config)

    # ── 事件匹配器 ──
    def is_group_add(event) -> bool:
        """仅匹配用户申请加群事件（排除邀请机器人入群）"""
        return isinstance(event, GroupRequestEvent) and event.sub_type == "add"

    group_request = on_request(rule=Rule(is_group_add), priority=5, block=False)

    @group_request.handle()
    async def _(bot: Bot, event: GroupRequestEvent):
        group_id = event.group_id
        user_id = event.user_id
        comment = event.comment

        # 1. 群级权限检查：该群是否配置了入群审核
        if not await is_group_feature_enabled(group_id, "group_sentinel:audit"):
            return

        # 2. 执行审核逻辑
        approved, reason = await audit_join_request(comment, user_id, group_id)

        if approved:
            await event.approve(bot)
            logger.info(
                f"[group_sentinel] 批准入群: user={user_id} group={group_id} "
                f"comment={comment}"
            )
        else:
            await event.reject(bot, reason="学号前6位错误或虚假。有异议可上报群主1950482412")
            logger.info(
                f"[group_sentinel] 拒绝入群: user={user_id} group={group_id} "
                f"reason={reason}"
            )

            # 发送群通知，供群主/群友人工复核
            notify_msg = (
                f"⚠️ 入群审核拒绝通知\n"
                f"申请人：{user_id}\n"
                f"拒绝原因：{reason}\n"
                f"申请信息：{comment or '(空)'}"
            )
            try:
                await bot.send_group_msg(group_id=group_id, message=notify_msg)
            except Exception as e:
                logger.warning(f"[group_sentinel] 发送拒绝通知失败: {e}")

    # ── 启动时自动创建默认权限组 ──
    @get_driver().on_startup
    async def _ensure_default_perm_group():
        """确保 group_sentinel 的默认权限组存在

        自动创建 group_sentinel 权限组并绑定 group_sentinel:audit 权限点。
        已存在的权限组不会被重复创建。
        管理员只需执行「perm 绑定 群 <群号> group_sentinel」即可开启监控。
        """
        group_name = "group_sentinel"
        perm_key = "group_sentinel:audit"
        display_name = "入群审核"

        async with async_session_factory() as session:
            existing = (await session.execute(
                select(PermissionGroup).where(PermissionGroup.name == group_name)
            )).scalars().first()

            if not existing:
                pg = PermissionGroup(
                    name=group_name,
                    display_name=display_name,
                    description="自动创建：入群审核功能权限组",
                    created_by=0,  # 系统自动创建
                )
                session.add(pg)
                await session.flush()
                session.add(PermissionGroupPerm(group_id=pg.id, perm_key=perm_key))
                await session.commit()
                logger.info(
                    f"[group_sentinel] 自动创建权限组: {group_name} "
                    f"(perm_key={perm_key})"
                )

"""管理员组的启动播种。

管理员 = 持有 ``checker.ADMIN_PERM_KEY`` 的用户，由 ``perm_admin`` 权限组授予。
本模块负责让这个组存在，并把 ``.env`` 里的 ``SUPERUSERS`` 迁移成它的初始成员 ——
否则改造后没人持有管理员点，连 WebUI 登录都会被自己拦在外面。

**只在组不存在时播种。** 组一旦存在就完全不动，所以管理员把成员清空后重启
不会被重新灌回来（否则「撤销」就不可靠了）。SUPERUSERS 因此只是**一次性种子**，
之后与鉴权再无关系。
"""
from nonebot import logger
from sqlalchemy import select

from src.common.database import get_session
from src.common.permission.checker import ADMIN_PERM_KEY
from src.common.permission.models import (
    PermissionGroup,
    PermissionGroupMember,
    PermissionGroupPerm,
)
from src.common.permission.supervisor import superuser_ids

#: 管理员权限组的名字（管理面板与播种共用这一个来源）
ADMIN_GROUP_NAME = "perm_admin"


async def ensure_admin_group() -> None:
    """确保 ``perm_admin`` 权限组存在；不存在则创建、绑定管理员点、播种 SUPERUSERS"""
    async with get_session() as session:
        existing = (await session.execute(
            select(PermissionGroup.id).where(PermissionGroup.name == ADMIN_GROUP_NAME).limit(1)
        )).first()

        if existing is not None:
            logger.debug(f"[permission] 管理员组 {ADMIN_GROUP_NAME} 已存在，跳过播种")
            return

        group = PermissionGroup(
            name=ADMIN_GROUP_NAME,
            display_name="管理员",
            description="持有管理员权限点，绕过全部权限检查；成员可由管理面板维护",
            created_by=0,  # 系统自动创建
        )
        session.add(group)
        await session.flush()

        session.add(PermissionGroupPerm(group_id=group.id, perm_key=ADMIN_PERM_KEY))

        # SUPERUSERS 作为初始成员播种，此后本配置与鉴权无关
        seeded = sorted(superuser_ids())
        for uid in seeded:
            session.add(PermissionGroupMember(group_id=group.id, user_id=int(uid)))


    logger.info(
        f"[permission] 已创建管理员组 {ADMIN_GROUP_NAME}"
        f"（绑定 {ADMIN_PERM_KEY}），从 SUPERUSERS 播种 {len(seeded)} 名成员: "
        f"{', '.join(seeded) if seeded else '无'}"
    )
    if not seeded:
        logger.warning(
            f"[permission] SUPERUSERS 为空，管理员组 {ADMIN_GROUP_NAME} 当前没有任何成员。"
            "请用管理面板添加管理员，否则无人能执行管理操作。"
        )

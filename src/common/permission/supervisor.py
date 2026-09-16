"""NoneBot ``SUPERUSERS`` 配置的读取。

**这里不再是鉴权入口。** 管理员判定已改由权限系统自己承担
（``checker.ADMIN_PERM_KEY`` + ``perm_admin`` 权限组），因为改 ``SUPERUSERS``
必须重启服务，而权限组的授予/撤销在运行期就能生效。

``SUPERUSERS`` 现在只有一个用途：**启动时的一次性播种种子** ——
``bootstrap.ensure_admin_group()`` 在管理员组尚不存在时，把这些 QQ 号写进
``perm_admin`` 组作为初始成员。此后它与鉴权完全无关。

不要在插件里用 ``is_superuser()`` 做鉴权，用 ``check_permission(event, ADMIN_PERM_KEY)``
或 ``user_has_permission(user_id, ADMIN_PERM_KEY)``。
"""
from nonebot import get_driver


def superuser_ids() -> set[str]:
    """配置里声明的超级管理员 QQ 号（字符串形式，与 NoneBot 配置一致）"""
    return {str(uid) for uid in get_driver().config.superusers}


def is_superuser(user_id: int | str) -> bool:
    """user_id 是否在配置的 ``SUPERUSERS`` 里（内部 ``str()`` 强转，int/str 都收）

    仅供启动播种与诊断使用，不要用于鉴权。
    """
    return str(user_id) in get_driver().config.superusers

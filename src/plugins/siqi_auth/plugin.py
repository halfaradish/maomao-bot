from typing import Optional, Union
from nonebot.adapters.onebot.v11 import MessageEvent, GroupMessageEvent, PrivateMessageEvent
from nonebot.plugin import PluginMetadata

from ...common.siqi_client import (
    AuthCheckResult,
    SiqiAuthRequestError,
    SiqiClient,
    siqi_client as shared_siqi_client,
)
from src.common.model.model import PluginGroupEnum, PluginBadgeColor

# 插件元信息
__plugin_meta__ = PluginMetadata(
    name="司契权限系统",
    description="司契权限系统集成插件，提供权限检查功能",
    usage="from src.plugins.siqi_auth.plugin import check_permission, check_permission_detail, has_permission\n\n# 检查用户权限\nallowed = await check_permission(\"member:ban\", \"3352239338\")\n\n# 检查用户权限并获取拒绝原因/角色信息\ndetail = await check_permission_detail(\"member:ban\", \"3352239338\")\n\n# 从消息事件检查权限\nallowed = await has_permission(event, \"member:ban\")",
    type="application",
    supported_adapters={"~onebot.v11"},
    extra={
        "group": PluginGroupEnum.BASE.value,
        "badge_color": PluginBadgeColor.BLUE.value,
        "version": "1.0.0",
        "author": "NoneBot"
    }
)

# 导出全局单例
siqi_auth = shared_siqi_client


def get_siqi_auth_client() -> SiqiClient:
    return siqi_auth


def _extract_user_id(event: Union[MessageEvent, GroupMessageEvent, PrivateMessageEvent]) -> str:
    return str(event.user_id)


async def check_permission_detail(
    perm_key: str,
    user_id: Union[str, int],
    app_code: Optional[str] = None,
) -> AuthCheckResult:
    """
    检查用户是否拥有某个权限，并返回详细结果。

    Args:
        perm_key: 权限标识，如 "member:ban"
        user_id: 用户ID，如 QQ号 "123456" 或整数 123456
        app_code: 应用代码，默认使用配置中的 qq_bot

    Returns:
        结构化鉴权结果，允许/拒绝都属于正常返回。

    Raises:
        SiqiAuthRequestError: 当请求失败、网络异常或司契响应非法时抛出。
    """
    return await siqi_auth.check_detail(perm_key, str(user_id), app_code)


async def check_permission(perm_key: str, user_id: Union[str, int], app_code: Optional[str] = None) -> bool:
    """
    检查用户是否拥有某个权限

    Args:
        perm_key: 权限标识，如 "member:ban"
        user_id: 用户ID，如 QQ号 "123456" 或整数 123456
        app_code: 应用代码，默认使用配置中的 qq_bot

    Returns:
        True 表示允许，False 表示拒绝

    Raises:
        SiqiAuthRequestError: 当请求失败、网络异常或司契响应非法时抛出。
    """
    return await siqi_auth.check(perm_key, str(user_id), app_code)


async def has_permission_detail(
    event: Union[MessageEvent, GroupMessageEvent, PrivateMessageEvent],
    perm_key: str,
    app_code: Optional[str] = None,
) -> AuthCheckResult:
    """
    从消息事件中提取用户ID并检查权限，返回详细结果。

    Args:
        event: 消息事件对象
        perm_key: 权限标识，如 "member:ban"
        app_code: 应用代码，默认使用配置中的 qq_bot

    Returns:
        结构化鉴权结果，允许/拒绝都属于正常返回。

    Raises:
        SiqiAuthRequestError: 当请求失败、网络异常或司契响应非法时抛出。
    """
    return await check_permission_detail(perm_key, _extract_user_id(event), app_code)


async def has_permission(event: Union[MessageEvent, GroupMessageEvent, PrivateMessageEvent], perm_key: str, app_code: Optional[str] = None) -> bool:
    """
    从消息事件中提取用户ID并检查权限

    Args:
        event: 消息事件对象
        perm_key: 权限标识，如 "member:ban"
        app_code: 应用代码，默认使用配置中的 qq_bot

    Returns:
        True 表示允许，False 表示拒绝

    Raises:
        SiqiAuthRequestError: 当请求失败、网络异常或司契响应非法时抛出。
    """
    return await siqi_auth.check(perm_key, _extract_user_id(event), app_code)

# 插件元信息
__plugin_name__ = "司契权限系统"
__plugin_description__ = "司契权限系统集成插件，提供权限检查功能"
__plugin_usage__ = """使用示例：

from src.plugins.siqi_auth.plugin import check_permission, check_permission_detail, has_permission

# 检查用户权限
allowed = await check_permission("member:ban", "3352239338")

# 检查用户权限并获取拒绝原因/角色信息
detail = await check_permission_detail("member:ban", "3352239338")

# 从消息事件检查权限
allowed = await has_permission(event, "member:ban")
"""
__plugin_version__ = "1.0.0"
__plugin_author__ = "NoneBot"

"""
权限管理面板插件

通过 QQ 聊天命令管理整个权限系统，可执行者为超级管理员或拥有
`permission_manager:manage` 权限的用户。

命令格式: 权限 <子命令> [参数...]

实现按职责拆分到同目录下的模块：`runtime` 持有配置与唯一的 `perm_cmd` 定义，
`helpers` / `guard` 提供参数解析与放行、缓存失效，`dispatch` 分发子命令，其余模块
按数据域承载各子命令实现。本文件只做装配：定义 `__plugin_meta__` 并导入上述模块
以触发匹配器与权限点注册。
"""
from nonebot.plugin import PluginMetadata

from src.common.plugin_meta import PluginGroupEnum, PluginBadgeColor
from .config import Config
from . import permissions  # noqa: F401

# 导入顺序是硬约束：dispatch 注册 @perm_cmd.handle()，login 注册
# @perm_cmd.got("login_confirm")，后者必须排在前者之后，否则每条 `权限` 命令都会
# 先落到二次确认的 got 提示上。
from .dispatch import handle_permission_command  # noqa: F401
from .login import handle_login_confirm  # noqa: F401

__plugin_meta__ = PluginMetadata(
    name="权限管理",
    description="权限系统的 QQ 聊天管理面板，支持黑/白名单、权限组、群绑定等全部管理操作",
    usage=(
        "perm 黑名单/blacklist 添加/add <QQ号> [原因]\n"
        "perm 黑名单/blacklist 移除/remove <QQ号>\n"
        "perm 黑名单/blacklist 列表/list\n"
        "perm 白名单/whitelist 用户/user 添加/add <QQ号> [原因]\n"
        "perm 白名单/whitelist 用户/user 移除/remove <QQ号>\n"
        "perm 白名单/whitelist 用户/user 列表/list\n"
        "perm 白名单/whitelist 群/group 添加/add <群号> [原因]\n"
        "perm 白名单/whitelist 群/group 移除/remove <群号>\n"
        "perm 白名单/whitelist 群/group 列表/list\n"
        "perm 权限组/group 创建/create <名称> [展示名] [描述]\n"
        "perm 权限组/group 删除/delete <名称>\n"
        "perm 权限组/group 列表/list\n"
        "perm 权限组/group 详情/info <名称>\n"
        "perm 权限组/group 添加成员/addmember <名称> <QQ> [QQ...]\n"
        "perm 权限组/group 移除成员/removemember <名称> <QQ>\n"
        "perm 权限组/group 添加权限/addperm <名称> <perm_key> [perm_key...]\n"
        "perm 权限组/group 移除权限/removeperm <名称> <perm_key>\n"
        "perm 权限组/group 批量加群/batchaddgroup <名称> <群号>\n"
        "perm 绑定/bind 群/group <群号> <权限组名>\n"
        "perm 绑定/bind 解除/unbind <群号>\n"
        "perm 绑定/bind 列表/list [群号]\n"
        "perm 注册点/points 列表/list [插件名]\n"
        "perm 查看/view <QQ号>\n"
        "perm 登录/login - 获取Web管理面板登录验证码（二次确认）"
    ),
    config=Config,
    supported_adapters={"~onebot.v11"},
    extra={
        "group": PluginGroupEnum.GROUP_MANAGE.value,
        "badge_color": PluginBadgeColor.BLUE.value,
    },
)

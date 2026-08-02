"""group_ban 权限点注册

注册权限点到权限系统，支持 WebUI 管理面板可视化和 GroupPermBinding 群绑定。
"""
from src.common.permission import register_perm_point

register_perm_point(
    "group_ban:use",
    "群禁言使用",
    "允许使用 ban/unban/kick 命令",
    plugin_name="group_ban",
)

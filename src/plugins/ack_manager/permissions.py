"""ack_manager 权限点注册

注册权限点到权限系统，支持 WebUI 管理面板可视化和 GroupPermBinding 群绑定。
"""
from src.common.permission import register_perm_point

register_perm_point(
    "ack_manager:ack",
    "全群确认",
    "允许使用 ack 命令发起全群确认（会 @全体成员）",
    plugin_name="ack_manager",
)

register_perm_point(
    "ack_manager:announce",
    "群公告",
    "允许使用 ann 命令发布群公告",
    plugin_name="ack_manager",
)

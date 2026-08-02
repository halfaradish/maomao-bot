"""fakemsg 权限点注册

注册权限点到权限系统，支持 WebUI 管理面板可视化和 GroupPermBinding 群绑定。
"""
from src.common.permission import register_perm_point

register_perm_point(
    "fakemsg:use",
    "伪消息使用",
    "允许无限制使用伪消息功能（不受每日额度限制）",
    plugin_name="fakemsg",
)
register_perm_point(
    "fakemsg:manage",
    "伪消息管理",
    "管理伪消息白名单（添加/移除/查看用户）",
    plugin_name="fakemsg",
)

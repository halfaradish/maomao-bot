"""refer_collector 权限点注册

注册权限点到权限系统，支持 WebUI 管理面板可视化和 GroupPermBinding 群绑定。
"""
from src.common.permission import register_perm_point

register_perm_point(
    "refer_collector:save",
    "保存内推图片",
    "允许向群内推图片库保存图片",
    plugin_name="refer_collector",
)

register_perm_point(
    "refer_collector:clear",
    "清空图片库",
    "允许清空整个内推图片库（破坏性操作）",
    plugin_name="refer_collector",
)

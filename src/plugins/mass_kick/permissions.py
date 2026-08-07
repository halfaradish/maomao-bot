"""mass_kick 权限点注册

注册权限点到权限系统，支持 WebUI 管理面板可视化和 GroupPermBinding 群绑定。
"""
from src.common.permission import register_perm_point

register_perm_point(
    "mass_kick:use",
    "一键退群使用",
    "允许使用 一键退群 命令",
    plugin_name="mass_kick",
)

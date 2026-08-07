"""group_statistics 权限点注册

注册权限点到权限系统，支持 WebUI 管理面板可视化和 GroupPermBinding 群绑定。
"""
from src.common.permission import register_perm_point

register_perm_point(
    "group_statistics:manage",
    "群统计管理",
    "允许添加/修改/删除群聊统计信息",
    plugin_name="group_statistics",
)

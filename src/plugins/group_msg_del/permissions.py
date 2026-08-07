"""group_msg_del 权限点注册

注册权限点到权限系统，支持 WebUI 管理面板可视化和 GroupPermBinding 群绑定。
"""
from src.common.permission import register_perm_point

register_perm_point(
    "group_msg_del:use",
    "群消息撤回使用",
    "允许使用撤回命令撤回群聊消息",
    plugin_name="group_msg_del",
)

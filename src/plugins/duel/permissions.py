"""duel 权限点注册

注册权限点到权限系统，支持 WebUI 管理面板可视化和 GroupPermBinding 群绑定。
"""
from src.common.permission import register_perm_point

register_perm_point(
    "duel:manage_map",
    "标签别名映射管理",
    "允许添加/删除题目标签别名映射（映射对所有人生效，属共享数据）",
    plugin_name="duel",
)

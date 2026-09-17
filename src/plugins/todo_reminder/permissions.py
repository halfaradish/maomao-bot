"""todo_reminder 权限点注册

注册权限点到权限系统，支持 WebUI 管理面板可视化和 GroupPermBinding 群绑定。
"""
from src.common.permission import register_perm_point

register_perm_point(
    "todo_reminder:use",
    "创建提醒",
    "允许创建/取消/完成/删除个人提醒（只读的列表与详情命令不受限）",
    plugin_name="todo_reminder",
)

register_perm_point(
    "todo_reminder:group_at_all",
    "群提醒 @全体",
    "允许创建 @全体成员 的群提醒（会打扰整个群）",
    plugin_name="todo_reminder",
)

register_perm_point(
    "todo_reminder:clear_cache",
    "清除缓存",
    "允许执行清除缓存命令（调试用，默认仅管理员）",
    plugin_name="todo_reminder",
)

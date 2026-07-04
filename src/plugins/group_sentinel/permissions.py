"""group_sentinel 权限点注册

注册权限点到权限系统，支持 WebUI 管理面板可视化和 GroupPermBinding 群绑定。
"""
from src.common.permission import register_perm_point

register_perm_point(
    "group_sentinel:audit",
    "入群审核",
    "开启后群哨兵将拦截入群请求并根据审核规则自动处理",
    plugin_name="group_sentinel",
)

"""plugin_usage_stats 权限点注册

注册权限点到权限系统，支持 WebUI 管理面板可视化和 GroupPermBinding 群绑定。
"""
from src.common.permission import register_perm_point

register_perm_point(
    "plugin_usage_stats:view",
    "查看插件统计",
    "允许查看插件使用统计榜单（汇总数据，默认仅管理员）",
    plugin_name="plugin_usage_stats",
)

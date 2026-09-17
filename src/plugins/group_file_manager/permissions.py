"""group_file_manager 权限点注册

注册权限点到权限系统，支持 WebUI 管理面板可视化和 GroupPermBinding 群绑定。
"""
from src.common.permission import register_perm_point

register_perm_point(
    "group_file_manager:crawl",
    "爬取历史文件",
    "允许手动触发本群历史文件爬取",
    plugin_name="group_file_manager",
)

register_perm_point(
    "group_file_manager:monitor",
    "监控群管理",
    "允许添加/移除监控群、查看监控群列表",
    plugin_name="group_file_manager",
)

register_perm_point(
    "group_file_manager:fix_fk",
    "修复外键约束",
    "允许手动触发群文件表的外键迁移（调试/修复用，默认仅管理员）",
    plugin_name="group_file_manager",
)

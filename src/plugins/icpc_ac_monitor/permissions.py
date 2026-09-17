"""icpc_ac_monitor 权限点注册

注册权限点到权限系统，支持 WebUI 管理面板可视化和 GroupPermBinding 群绑定。
"""
from src.common.permission import register_perm_point

register_perm_point(
    "icpc_ac_monitor:control",
    "比赛监控开关",
    "允许开始/取消比赛 AC 监控（会启停全局监控线程并推送到目标群）",
    plugin_name="icpc_ac_monitor",
)

register_perm_point(
    "icpc_ac_monitor:whitelist",
    "艾特名单管理",
    "允许添加/移除/查看比赛监控的艾特白名单",
    plugin_name="icpc_ac_monitor",
)

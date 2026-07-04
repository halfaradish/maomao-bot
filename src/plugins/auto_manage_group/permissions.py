"""auto_manage_group 权限点注册

注册 4 个权限点到权限系统，支持 WebUI 管理面板可视化和 GroupPermBinding 群绑定。
"""
from src.common.permission import register_perm_point

register_perm_point(
    "auto_manage_group:increase",
    "入群欢迎",
    "允许在群内自动发送新成员欢迎消息",
    plugin_name="auto_manage_group",
)
register_perm_point(
    "auto_manage_group:decrease",
    "离群通知",
    
    "允许在群内自动发送成员离开通知",
    plugin_name="auto_manage_group",
)
register_perm_point(
    "auto_manage_group:ban_word_detect",
    "违禁词检测",
    "允许在群内自动检测并处理违禁词消息（AI 模型 + 禁言/撤回/上下文清除）",
    plugin_name="auto_manage_group",
)
register_perm_point(
    "auto_manage_group:ban_word_log_target",
    "违禁词告警日志接收",
    "接收违禁词检测告警日志（合并转发消息）",
    plugin_name="auto_manage_group",
)

"""限速器权限点声明

限速器是**全局生效**的运维开关：一开一关影响所有群的发消息节奏。原先 8 条控制
命令（`限速启用/禁用/紧急停止/恢复/状态/全局/按群/rate`）都没有 `permission=`
闸，任何群成员都能把限速关掉或触发全局紧急停止，所以现在按插件约定登记权限点：

- ``rate_limiter:manage`` —— 控制类（启用/禁用/紧急停止/恢复/切换模式）
- ``rate_limiter:view``   —— 只读类（查看状态、命令帮助）

键名沿用 ``plugin_name:action``；超级管理员（持有 ``permission_manager:manage``）
天然放行，不需要单独授权。
"""
from src.common.permission import register_perm_point

register_perm_point(
    "rate_limiter:manage",
    "限速器控制",
    "启用/禁用限速、紧急停止与恢复、切换按群/全局限速模式",
    plugin_name="rate_limiter_middleware",
)
register_perm_point(
    "rate_limiter:view",
    "限速器查看",
    "查看限速器状态与命令帮助",
    plugin_name="rate_limiter_middleware",
)

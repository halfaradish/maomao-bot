"""
vv 插件权限点声明

vv:use 采用黑名单模式管控：默认开放，群号命中 vv 专属黑名单
（vv_group_blacklist 表）即拦截，与权限组的白名单语义无关。
注册此权限点用于权限面板展示与后续管控扩展。
"""
from src.common.permission import register_perm_point

register_perm_point(
    "vv:use",
    "VV表情包",
    "这就是VV 表情包使用（黑名单模式：默认开放，群黑名单拦截）",
    plugin_name="vv",
)

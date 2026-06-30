from src.common.permission import register_perm_point

register_perm_point(
    "permission_manager:manage",
    "权限管理",
    "管理权限系统的黑白名单、权限组、群绑定等所有操作",
    plugin_name="permission_manager",
)

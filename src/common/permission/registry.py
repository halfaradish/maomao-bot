"""
权限点注册表

在插件 import 阶段收集所有声明的权限点，
启动时由 auto_register.py 统一同步到数据库。
"""
from dataclasses import dataclass, field


@dataclass
class PermissionPointDef:
    """插件声明的权限点定义"""
    key: str              # e.g. "group_ban:ban"
    name: str             # e.g. "禁言"
    description: str = "" # 功能描述
    plugin_name: str = "" # 来源插件名


class PermissionRegistry:
    """权限点注册表（内存单例）"""

    def __init__(self):
        self._points: dict[str, PermissionPointDef] = {}

    def register(
        self,
        key: str,
        name: str,
        description: str = "",
        plugin_name: str = "",
    ) -> None:
        """注册一个权限点（幂等，重复注册不报错）"""
        if key not in self._points:
            self._points[key] = PermissionPointDef(
                key=key,
                name=name,
                description=description,
                plugin_name=plugin_name,
            )

    def get_all(self) -> list[PermissionPointDef]:
        """获取所有已注册的权限点"""
        return list(self._points.values())

    def get(self, key: str) -> PermissionPointDef | None:
        """按 key 获取单个权限点"""
        return self._points.get(key)

    def exists(self, key: str) -> bool:
        """检查权限点是否已注册"""
        return key in self._points


# 全局单例
perm_registry = PermissionRegistry()

# 便捷函数
register_perm_point = perm_registry.register

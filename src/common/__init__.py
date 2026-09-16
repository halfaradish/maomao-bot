"""公共工具的按需导出。

导入一个独立工具不会初始化其他工具的数据库、Redis 或 NoneBot 依赖。
原有 ``from src.common import ...`` 接口保留；对应服务在首次使用时加载。
"""

from importlib import import_module
import sys
from types import ModuleType


_EXPORTS = {
    "get_icpc_db_connection": ("icpc_db_pool", "get_icpc_db_connection"),
    "JsonUtils": ("json_utils", "JsonUtils"),
    "CompressPic": ("compress_pics", "CompressPic"),
    "SendForwardMsg": ("send_forward_msg", "SendForwardMsg"),
    "utils": ("utils", None),
    "get_redis_connection": ("oj_redis_pool", "get_redis_connection"),
    "TokenBucketLimiter": ("rate_limiter", "TokenBucketLimiter"),
    "GroupRateLimiter": ("rate_limiter", "GroupRateLimiter"),
    "AuthCheckResult": ("siqi_client", "AuthCheckResult"),
    "SiqiAuthRequestError": ("siqi_client", "SiqiAuthRequestError"),
    "siqi_client": ("siqi_client", "siqi_client"),
    "current_env_tag": ("database", "current_env_tag"),
    "ensure_tables": ("database", "ensure_tables"),
    "get_session": ("database", "get_session"),
}

__all__ = list(_EXPORTS)


def __getattr__(name: str):
    if name not in _EXPORTS:
        raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
    module_name, attribute = _EXPORTS[name]
    module = import_module(f".{module_name}", __name__)
    value = getattr(module, attribute) if attribute is not None else module
    globals()[name] = value
    return value


def __dir__():
    return sorted(set(globals()) | set(__all__))


class _CommonModule(ModuleType):
    def __setattr__(self, name, value):
        # 历史接口的 siqi_client 是单例，却与子模块同名。importlib 加载
        # 子模块时会设置父包属性；保持单例导出，避免导入顺序改变返回类型。
        # import_module("src.common.siqi_client") 和 from 子模块 import
        # 仍通过 sys.modules 取得真实模块，不受此兼容处理影响。
        if (
            name == "siqi_client"
            and isinstance(value, ModuleType)
            and value.__name__ == f"{__name__}.siqi_client"
        ):
            value = value.siqi_client
        super().__setattr__(name, value)


sys.modules[__name__].__class__ = _CommonModule

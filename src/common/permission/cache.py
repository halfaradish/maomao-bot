"""
内存 TTL 缓存 — 用于权限校验结果缓存

单进程 bot 场景适用，无需 Redis。
"""
import time
from typing import Any, Dict, Optional


class TTLCache:
    """带 TTL 的简单内存缓存"""

    def __init__(self, default_ttl: int = 60):
        self._data: Dict[str, tuple[Any, float]] = {}
        self._default_ttl = default_ttl

    def get(self, key: str) -> Optional[Any]:
        """获取缓存值，过期返回 None"""
        entry = self._data.get(key)
        if entry is None:
            return None
        value, expires_at = entry
        if time.time() > expires_at:
            del self._data[key]
            return None
        return value

    def set(self, key: str, value: Any, ttl: Optional[int] = None) -> None:
        """设置缓存值"""
        ttl = ttl if ttl is not None else self._default_ttl
        self._data[key] = (value, time.time() + ttl)

    def delete(self, key: str) -> None:
        """删除单个缓存条目"""
        self._data.pop(key, None)

    def clear_pattern(self, prefix: str) -> None:
        """清除所有键包含指定前缀的缓存条目"""
        to_del = [k for k in self._data if prefix in k]
        for k in to_del:
            del self._data[k]

    def clear_all(self) -> None:
        """清空所有缓存"""
        self._data.clear()

    def __len__(self) -> int:
        return len(self._data)


# 全局单例，默认 60 秒 TTL
perm_cache = TTLCache(default_ttl=60)

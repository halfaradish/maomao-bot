import os
import sys
import threading
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Type
from asgiref.sync import sync_to_async


BASE_DIR = Path(__file__).resolve().parents[2]
PROJECT_DIR = BASE_DIR / "django_project"
if PROJECT_DIR.exists():
    project_path = str(PROJECT_DIR)
    if project_path not in sys.path:
        sys.path.insert(0, project_path)

_django_initialized = False
_init_lock = threading.Lock()


def init_django_if_needed() -> None:
    global _django_initialized
    if _django_initialized:
        return
    with _init_lock:
        if _django_initialized:
            return
        
        # 检查 Django 是否已经配置
        import django
        from django.apps import apps
        if apps.ready:
            # Django 已经初始化，直接返回
            _django_initialized = True
            return
        
        # 尝试使用 PyMySQL 替代 MySQLdb（适用于 Windows 和 Linux）
        # 如果 PyMySQL 已安装，优先使用它；否则使用 mysqlclient（Linux）或让 Django 报错
        try:
            import pymysql
            # 将 PyMySQL 配置为 MySQLdb 的替代
            pymysql.install_as_MySQLdb()
        except ImportError:
            # PyMySQL 未安装，在 Linux 上应该使用 mysqlclient，在 Windows 上会报错
            pass
        
        os.environ.setdefault("DJANGO_SETTINGS_MODULE", "django_project.settings")
        # 允许在非 Django 进程中初始化 ORM
        try:
            django.setup()
        except RuntimeError as e:
            # 如果 Django 已经初始化（populate() isn't reentrant），忽略错误
            if "populate() isn't reentrant" in str(e):
                pass
            else:
                raise
        _django_initialized = True


# 异步版本的 CRUD 函数
async def async_create_record(model_cls: Type[Any], **fields) -> Any:
    """异步创建记录"""
    init_django_if_needed()
    
    def _create_sync():
        return model_cls.objects.create(**fields)
    
    return await sync_to_async(_create_sync)()


async def async_get_one(model_cls: Type[Any], **filters) -> Optional[Any]:
    """异步获取单条记录"""
    init_django_if_needed()
    
    def _get_one_sync():
        try:
            return model_cls.objects.filter(**filters).first()
        except Exception:
            return None
    
    return await sync_to_async(_get_one_sync)()


async def async_get_many(
    model_cls: Type[Any],
    filters: Optional[Dict[str, Any]] = None,
    order_by: Optional[Iterable[str]] = None,
    limit: Optional[int] = None,
) -> List[Any]:
    """异步获取多条记录"""
    init_django_if_needed()
    
    def _get_many_sync():
        qs = model_cls.objects
        if filters:
            qs = qs.filter(**filters)
        if order_by:
            qs = qs.order_by(*order_by)
        if limit is not None:
            qs = qs[:limit]
        return list(qs)
    
    return await sync_to_async(_get_many_sync)()


async def async_update_records(model_cls: Type[Any], filters: Dict[str, Any], updates: Dict[str, Any]) -> int:
    """异步更新记录"""
    init_django_if_needed()
    
    def _update_sync():
        return model_cls.objects.filter(**filters).update(**updates)
    
    return await sync_to_async(_update_sync)()


async def async_delete_records(model_cls: Type[Any], **filters) -> int:
    """异步删除记录"""
    init_django_if_needed()
    
    def _delete_sync():
        deleted, _ = model_cls.objects.filter(**filters).delete()
        return deleted
    
    return await sync_to_async(_delete_sync)()



from nonebot import logger
from contextlib import contextmanager
from functools import wraps
import time
import asyncio

@contextmanager
def timer(name):
    """上下文管理器-with计时器"""
    start = time.perf_counter()
    yield
    end = time.perf_counter()
    logger.debug(f"{name} 耗时: {end - start:.6} 秒")

def timed_section(name):
    """装饰器计时器"""
    def decorator(func):
        @wraps(func)
        def sync_wrapper(*args, **kwargs):
            # 处理同步函数
            start = time.perf_counter()
            result = func(*args, **kwargs)
            end = time.perf_counter()
            logger.debug(f"{name} 耗时: {end - start:.6f} 秒")
            return result
        
        @wraps(func)
        async def async_wrapper(*args, **kwargs):
            # 处理异步函数
            start = time.perf_counter()
            result = await func(*args, **kwargs)
            end = time.perf_counter()
            logger.debug(f"{name} 耗时: {end - start:.6f} 秒")
            return result

        if asyncio.iscoroutinefunction(func):
            return async_wrapper
        else:
            return sync_wrapper
        
    return decorator
from nonebot import logger
import redis
from redis import RedisError
import time
from typing import Any, Callable, Optional, TypeVar, cast

from ..config import RedisConfig

# 定义通用异常处理函数
def handle_exception(e: Exception, operation: str = "操作") -> None:
    """处理Redis异常并记录日志，针对不同类型的异常采用不同的处理策略"""
    # 特殊处理FinishedException
    if isinstance(e, Exception) and e.__class__.__name__ == "FinishedException":
        # FinishedException通常表示任务已完成，不需要重试
        logger.warning(f"Redis任务已完成: {str(e)}")
    else:
        logger.error(f"Redis{operation}异常: {str(e)}")

try:
    redis_pool = redis.ConnectionPool(
        max_connections=RedisConfig.MAX_CONNECTIONS,  # 最大连接数
        decode_responses=RedisConfig.DECODE_RESPONSES,  # 自动将返回结果解码为字符串
        socket_timeout=RedisConfig.SOCKET_TIMEOUT,  # 连接超时时间（秒）- 修正命名
        socket_connect_timeout=RedisConfig.SOCKET_CONNECT_TIMEOUT,  # 建立连接的超时时间（秒）
        host=RedisConfig.HOST,
        port=RedisConfig.PORT,
        password=RedisConfig.PASSWORD,
        db=RedisConfig.DB,
        # 添加重试机制相关配置
        retry_on_timeout=RedisConfig.RETRY_ON_TIME,
        health_check_interval=RedisConfig.HEALTH_CHECK_INTERVAL  # 每30秒进行一次健康检查
    )
    logger.info(f"Redis连接池初始化成功: {RedisConfig.HOST}:{RedisConfig.PORT}, DB: {RedisConfig.DB}")
except RedisError as e:
    logger.error(f"Redis连接池初始化失败: {e}")
    raise

class RedisConnection:
    """Redis连接上下文管理器，提供连接获取、自动重连和资源释放功能"""
    
    def __init__(self, max_retries=3, retry_delay=1):
        self.client = None  # Redis客户端实例
        self.max_retries = max_retries  # 最大重试次数
        self.retry_delay = retry_delay  # 重试间隔（秒）

    def __enter__(self):
        """获取Redis连接，支持自动重连"""
        retry_count = 0
        while retry_count <= self.max_retries:
            try:
                # 从连接池获取客户端（自动复用连接）
                self.client = redis.Redis(connection_pool=redis_pool)
                # 进行简单的连接测试
                self.client.ping()
                logger.debug(f"Redis连接成功: {RedisConfig.HOST}:{RedisConfig.PORT}")
                return self
            except RedisError as e:
                retry_count += 1
                if retry_count > self.max_retries:
                    logger.error(f"Redis连接失败，已达最大重试次数: {e}")
                    raise
                logger.warning(f"Redis连接失败，正在进行第 {retry_count}/{self.max_retries} 次重试: {e}")
                time.sleep(self.retry_delay * retry_count)  # 指数退避

    def __exit__(self, exc_type, exc_val, exc_tb):
        """释放Redis连接资源"""
        # Redis连接池会自动管理连接归还，无需手动关闭
        # 若有事务/管道操作，异常时可在此处理回滚
        if exc_type:
            handle_exception(exc_val)
        
        # 显式断开连接（虽然连接池会管理，但显式调用更安全）
        if self.client:
            try:
                self.client.close()
            except Exception as e:
                logger.warning(f"关闭Redis连接时发生错误: {e}")
            
        self.client = None  # 释放引用
    
    def get_client(self):
        """获取Redis客户端实例"""
        if not self.client:
            raise RuntimeError("Redis客户端未初始化，请在with语句中使用")
        return self.client

def get_redis_connection(max_retries=3, retry_delay=1):
    """获取Redis连接（通过上下文管理器使用）
    
    Args:
        max_retries: 最大重试次数
        retry_delay: 初始重试延迟（秒）
        
    Returns:
        RedisConnection: Redis连接上下文管理器
    """
    return RedisConnection(max_retries, retry_delay)

# 定义类型变量
T = TypeVar('T')

# 提供直接操作Redis的便捷函数
def redis_command(func_name: str, *args, **kwargs) -> Any:
    """执行Redis命令的便捷函数
    
    Args:
        func_name: Redis命令名称
        *args: 命令参数
        **kwargs: 命令关键字参数
        
    Returns:
        命令执行结果
        
    Raises:
        RedisError: 当命令执行失败时
        ValueError: 当命令不存在时
    """
    try:
        with get_redis_connection() as conn:
            client = conn.get_client()
            try:
                func = getattr(client, func_name)
                return func(*args, **kwargs)
            except AttributeError:
                raise ValueError(f"Redis命令 '{func_name}' 不存在")
            except Exception as e:
                # 捕获操作过程中的异常
                handle_exception(e, f"命令 {func_name} 执行")
                # 对于FinishedException，不应该重新抛出，因为这通常表示任务已正常完成
                if isinstance(e, Exception) and e.__class__.__name__ == "FinishedException":
                    return None
                raise
    except Exception as e:
        # 再次检查是否为FinishedException
        if isinstance(e, Exception) and e.__class__.__name__ == "FinishedException":
            return None
        raise

# 添加一个通用的Redis操作装饰器，简化错误处理
def redis_operation(retry_on_error: bool = True, max_retries: int = 2):
    """Redis操作装饰器，提供统一的异常处理和重试机制
    
    Args:
        retry_on_error: 是否在错误时重试
        max_retries: 最大重试次数
    
    Returns:
        装饰后的函数
    """
    def decorator(func: Callable[..., T]) -> Callable[..., T]:
        def wrapper(*args, **kwargs) -> T:
            retries = 0
            last_exception = None
            
            while retries <= max_retries:
                try:
                    return func(*args, **kwargs)
                except Exception as e:
                    # 特殊处理FinishedException，不重试
                    if isinstance(e, Exception) and e.__class__.__name__ == "FinishedException":
                        logger.info(f"Redis操作已完成，无需重试")
                        return cast(T, None)
                    
                    last_exception = e
                    retries += 1
                    
                    if retries > max_retries or not retry_on_error:
                        logger.error(f"Redis操作失败，已达最大重试次数: {str(e)}")
                        raise
                    
                    logger.warning(f"Redis操作失败，正在进行第 {retries}/{max_retries} 次重试: {str(e)}")
                    time.sleep(0.5 * retries)  # 简单的退避策略
            
            # 理论上不会到达这里，但为了类型安全
            raise last_exception or RuntimeError("Redis操作失败")
        
        return wrapper
    
    return decorator
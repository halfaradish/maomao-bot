import redis
from redis import RedisError

from ..config import RedisConfig

try:
    redis_pool = redis.ConnectionPool(
        max_connections=RedisConfig.MAX_CONNECTIONS,  # 最大连接数
        decode_responses=RedisConfig.DECODE_RESPONSES,  # 自动将返回结果解码为字符串
        socket_timeout=RedisConfig.SOCKET_timeout,  # 连接超时时间（秒）
        socket_connect_timeout=RedisConfig.SOCKET_CONNECT_TIMEOUT,  # 建立连接的超时时间（秒）
        host=RedisConfig.HOST,
        port=RedisConfig.PORT,
        password=RedisConfig.PASSWORD,
        db=RedisConfig.DB,
    )
except RedisError as e:
    print(f"Redis连接池初始化失败: {e}")
    raise

class RedisConnection:
    def __init__(self):
        self.client = None  # Redis客户端实例

    def __enter__(self):
        # 从连接池获取客户端（自动复用连接）
        self.client = redis.Redis(connection_pool=redis_pool)
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        # Redis连接池会自动管理连接归还，无需手动关闭
        # 若有事务/管道操作，异常时可在此处理回滚
        if exc_type:
            print(f"Redis操作异常: {exc_val}")
        self.client = None  # 释放引用
    

def get_redis_connection():
    """获取Redis连接（通过上下文管理器使用）"""
    return RedisConnection()
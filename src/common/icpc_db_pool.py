from nonebot import logger
from mysql.connector import Error, pooling
from typing import Optional

from ..config import IcpcDBConfig

_pool_config = {
    "pool_name": "gxuicpc_pool",
    "pool_size": IcpcDBConfig.ICPC_DB_POOL_SIZE,
    "pool_reset_session": True,
    "host": IcpcDBConfig.ICPC_DB_HOST,
    "user": IcpcDBConfig.ICPC_DB_USER,
    "password": IcpcDBConfig.ICPC_DB_PASSWORD,
    "database": IcpcDBConfig.ICPC_DB_NAME,
    "port": IcpcDBConfig.ICPC_DB_PORT,
}

_db_pool: Optional[pooling.MySQLConnectionPool] = None

def _init_db_pool() -> pooling.MySQLConnectionPool:
    """初始化连接池（内部函数）"""
    try:
        pool = pooling.MySQLConnectionPool(**_pool_config)
        logger.info("数据库连接池 gxuicpc_pool 初始化成功")
        return pool
    except Error as e:
        # 提供清晰的错误信息，而不是让 bot 崩溃
        logger.error(f"【致命错误】数据库连接池 gxuicpc_pool 初始化失败！请检查配置和网络")
        logger.error(f"配置信息: host={_pool_config['host']}, port={_pool_config['port']}, user={_pool_config['user']}, database={_pool_config['database']}")
        logger.exception(e)  # 打印完整堆栈
        raise RuntimeError(f"数据库连接池初始化失败: {e}") from e

def get_db_pool() -> pooling.MySQLConnectionPool:
    """懒加载获取连接池（线程安全可通过外部保证）"""
    global _db_pool
    if _db_pool is None:
        _db_pool = _init_db_pool()
    return _db_pool

class MySQLConnection:
    
    def __init__(self, connection):
        self.connection = connection
        self.cursor = None

    def __enter__(self):
        self.cursor = self.connection.cursor(dictionary=True)
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        if self.cursor:
            self.cursor.close()
        if self.connection:
            try:
                if exc_type:
                    self.connection.rollback()
                else:
                    self.connection.commit()
            finally:
                self.connection.close()

    def execute(self, query, params=None):
        if params is None:
            params = ()
        self.cursor.execute(query, params)
        return self.cursor
    
    def execute_many(self, query, params_list):
        self.cursor.executemany(query, params_list)
        return self.cursor
    
def get_icpc_db_connection():
    """
    获取数据库连接
    增加错误处理，在连接池耗尽时提供更友好的错误信息
    """
    try:
        pool = get_db_pool()
        conn = pool.get_connection()
        return MySQLConnection(conn)
    except Error as e:
        error_msg = str(e).lower()
        if "pool exhausted" in error_msg or "connection not available" in error_msg:
            logger.error(f"数据库连接池耗尽！请检查：1.连接是否正确关闭 2.是否忘记使用 with 语句 3.考虑增加 pool_size")
            logger.error(f"当前配置 pool_size={_pool_config['pool_size']}")
        raise  # 重新抛出原始异常，让业务层决定如何处理

def close_db_pool():
    """关闭连接池（用于优雅退出）"""
    global _db_pool
    if _db_pool:
        _db_pool.closeall()
        _db_pool = None
        logger.info("数据库连接池 diting_bot_pool 已关闭")

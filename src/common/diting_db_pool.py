from nonebot import logger
from mysql.connector import Error, pooling
from typing import Optional

from ..config import DiTingBotDBConfig

# 连接池配置（仅定义，不立即创建）
_pool_config = {
    "pool_name": "diting_bot_pool",
    "pool_size": DiTingBotDBConfig.BOT_DB_POOL_SIZE,
    "pool_reset_session": True,
    "host": DiTingBotDBConfig.BOT_DB_HOST,
    "user": DiTingBotDBConfig.BOT_DB_USER,
    "password": DiTingBotDBConfig.BOT_DB_PASSWORD,
    "database": DiTingBotDBConfig.BOT_DB_NAME,
    "port": DiTingBotDBConfig.BOT_DB_PORT,
}

# 连接池变量（初始为 None，延迟初始化）
_db_pool: Optional[pooling.MySQLConnectionPool] = None

def _init_db_pool() -> pooling.MySQLConnectionPool:
    """初始化连接池（内部函数）"""
    try:
        pool = pooling.MySQLConnectionPool(**_pool_config)
        logger.info("数据库连接池 diting_bot_pool 初始化成功")
        return pool
    except Error as e:
        logger.error(f"【致命错误】数据库连接池 diting_bot_pool 初始化失败！请检查配置和网络")
        logger.error(f"配置信息: host={_pool_config['host']}, port={_pool_config['port']}, user={_pool_config['user']}, database={_pool_config['database']}")
        logger.exception(e)
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
                # 重要：将连接归还给连接池
                self.connection.close()

    def execute(self, query, params=None):
        if params is None:
            params = ()
        self.cursor.execute(query, params)
        return self.cursor
    
    def execute_many(self, query, params_list):
        self.cursor.executemany(query, params_list)
        return self.cursor
    
def get_diting_db_connection():
    try:
        pool = get_db_pool()
        conn = pool.get_connection()
        return MySQLConnection(conn)
    except Error as e:
        error_msg = str(e).lower()
        if "pool exhausted" in error_msg or "connection not available" in error_msg:
            logger.error(f"数据库连接池耗尽！请检查：1.连接是否正确关闭 2.是否忘记使用 with 语句 3.考虑增加 pool_size")
            logger.error(f"当前配置 pool_size={_pool_config['pool_size']}")
        else:
            logger.error(f"获取数据库连接失败: {e}")
        raise

def get_pool_status():
    """获取连接池状态信息"""
    try:
        pool = get_db_pool()  # 确保连接池已初始化
        return {
            "pool_name": pool.pool_name,
            "pool_size": pool.pool_size,
            "pool_reset_session": pool.pool_reset_session
        }
    except Exception as e:
        logger.error(f"获取连接池状态失败: {e}")
        return None
    
def close_db_pool():
    """关闭连接池（用于优雅退出）"""
    global _db_pool
    if _db_pool:
        _db_pool.closeall()
        _db_pool = None
        logger.info("数据库连接池 diting_bot_pool 已关闭")

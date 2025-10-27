from nonebot import logger
from mysql.connector import Error, pooling

from ..config import DiTingBotDBConfig

try:
    # 连接池配置
    db_pool = pooling.MySQLConnectionPool(
        pool_name="diting_bot_pool",  # 连接池名称
        pool_size=DiTingBotDBConfig.BOT_DB_POOL_SIZE,
        pool_reset_session=True,  # 归还连接时重置会话
        host=DiTingBotDBConfig.BOT_DB_HOST,
        user=DiTingBotDBConfig.BOT_DB_USER,
        password=DiTingBotDBConfig.BOT_DB_PASSWORD,
        database=DiTingBotDBConfig.BOT_DB_NAME,
        port=DiTingBotDBConfig.BOT_DB_PORT
    )
except Error as e:
    print(f"连接池 diting_bot_pool 初始化失败: {e}")
    raise

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
            if exc_type:
                self.connection.rollback()
            else:
                self.connection.commit()
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
        conn = db_pool.get_connection()
        return MySQLConnection(conn)
    except Error as e:
        if "pool exhausted" in str(e).lower():
            logger.error(f"数据库连接池耗尽，请检查连接是否正确关闭或考虑增加连接池大小: {e}")
            logger.error(f"当前连接池状态: 总连接数={db_pool.pool_size}")
        else:
            logger.error(f"获取数据库连接失败: {e}")
        raise

def get_pool_status():
    """获取连接池状态信息"""
    try:
        # 使用连接池的内部属性获取状态
        return {
            "pool_name": db_pool.pool_name,
            "pool_size": db_pool.pool_size,
            "pool_reset_session": db_pool.pool_reset_session
        }
    except Exception as e:
        logger.error(f"获取连接池状态失败: {e}")
        return None

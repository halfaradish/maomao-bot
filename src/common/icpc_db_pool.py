from nonebot import logger
from mysql.connector import Error, pooling

from ..config import IcpcDBConfig

try:
    # 连接池配置
    db_pool = pooling.MySQLConnectionPool(
        pool_name="gxuicpc_pool",
        pool_size=IcpcDBConfig.ICPC_DB_POOL_SIZE,  # 增加连接池大小以应对高并发
        pool_reset_session=True,
        host=IcpcDBConfig.ICPC_DB_HOST,
        user=IcpcDBConfig.ICPC_DB_USER,
        password=IcpcDBConfig.ICPC_DB_PASSWORD,
        database=IcpcDBConfig.ICPC_DB_NAME,
        port=IcpcDBConfig.ICPC_DB_PORT
    )
except Error as e:
    print(f"连接池 gxuicpc_pool 初始化失败: {e}")
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
        conn = db_pool.get_connection()
        return MySQLConnection(conn)
    except Error as e:
        if "pool exhausted" in str(e).lower():
            logger.error(f"数据库连接池耗尽，请检查连接是否正确关闭或考虑增加连接池大小: {e}")
        raise

from mysql.connector import Error, pooling

from ..config import DiTingBotDBConfig

try:
    # 连接池配置
    db_pool = pooling.MySQLConnectionPool(
        pool_name="diting_bot_pool",  # 连接池名称
        pool_size=5,  # 默认连接数
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

    def execute(self, query, params=None):
        if params is None:
            params = ()
        self.cursor.execute(query, params)
        return self.cursor
    
    def execute_many(self, query, params_list):
        self.cursor.executemany(query, params_list)
        return self.cursor
    
def get_diting_db_connection():
    conn = db_pool.get_connection()
    return MySQLConnection(conn)

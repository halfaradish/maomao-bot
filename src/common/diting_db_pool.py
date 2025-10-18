import mysql.connector
from mysql.connector import Error

from ..config import DiTingBotDBConfig

class MySQLConnection:
    
    def __init__(self):
        self.connection = None
        self.cursor = None

    def __enter__(self):
        try:
            self.connection = mysql.connector.connect(
                host = DiTingBotDBConfig.BOT_DB_HOST,
                user = DiTingBotDBConfig.BOT_DB_USER,
                password = DiTingBotDBConfig.BOT_DB_PASSWORD,
                database = DiTingBotDBConfig.BOT_DB_NAME,
                port = DiTingBotDBConfig.BOT_DB_PORT
            )
            self.cursor = self.connection.cursor(dictionary=True)
            return self
        except Error as e:
            print(f"数据库(gxuicpc)连接失败: {e}")
            raise

    def __exit__(self, exc_type, exc_val, exc_tb):
        if self.cursor:
            self.cursor.close()
        if self.connection:
            if exc_type:
                self.connection.rollback()
            else:
                self.connection.commit()
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
    return MySQLConnection()

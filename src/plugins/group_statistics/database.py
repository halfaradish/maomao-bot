import logging
from typing import Dict, List, Optional, Any
from nonebot import logger
import pymysql
from pymysql.cursors import DictCursor
from src.config.local_config import DiTingBotDBConfig


# Bot数据库连接池配置
_pool_config = {
    "host": DiTingBotDBConfig.BOT_DB_HOST,
    "port": DiTingBotDBConfig.BOT_DB_PORT,
    "user": DiTingBotDBConfig.BOT_DB_USER,
    "password": DiTingBotDBConfig.BOT_DB_PASSWORD,
    "database": DiTingBotDBConfig.BOT_DB_NAME,
    "charset": "utf8mb4",
    "cursorclass": DictCursor
}


class BotDBConnection:
    """Bot数据库连接上下文管理器"""
    
    def __init__(self):
        self.connection = None
        self.cursor = None

    def __enter__(self):
        self.connection = pymysql.connect(**_pool_config)
        self.cursor = self.connection.cursor()
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


def get_bot_db_connection():
    """获取bot数据库连接"""
    return BotDBConnection()


class DatabaseManager:
    """数据库管理类，处理群统计相关的数据库操作"""
    
    def __init__(self):
        self.table_name = "group_statistics"
    
    def ensure_table_exists(self) -> None:
        """确保数据表存在，如果不存在则创建"""
        try:
            with get_bot_db_connection() as db:
                # 创建表的SQL语句
                create_table_sql = f"""
                CREATE TABLE IF NOT EXISTS {self.table_name} (
                    id INT AUTO_INCREMENT PRIMARY KEY,
                    group_id VARCHAR(20) NOT NULL UNIQUE,
                    group_name VARCHAR(100) NOT NULL,
                    group_function TEXT,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP
                ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
                """
                db.execute(create_table_sql)
                logger.info(f"确保表 {self.table_name} 存在成功")
        except Exception as e:
            logger.error(f"创建数据表失败: {e}")
            raise
    
    def add_group(self, group_id: str, group_name: str, group_function: str) -> bool:
        """添加群聊信息"""
        try:
            with get_bot_db_connection() as db:
                # 只进行插入操作，不进行更新
                sql = f"""
                INSERT INTO {self.table_name} (group_id, group_name, group_function) 
                VALUES (%s, %s, %s)
                """
                try:
                    db.execute(sql, (group_id, group_name, group_function))
                    logger.info(f"添加群聊信息: {group_id} - {group_name}")
                    return True
                except pymysql.err.IntegrityError:
                    # 当群号已存在时，返回False
                    logger.info(f"群聊信息已存在: {group_id}")
                    return False
        except Exception as e:
            logger.error(f"添加群聊信息失败: {e}")
            return False
    
    def update_group(self, group_id: str, group_name: str, group_function: str) -> bool:
        """更新群聊信息"""
        try:
            with get_bot_db_connection() as db:
                sql = f"""
                UPDATE {self.table_name} 
                SET group_name = %s, group_function = %s 
                WHERE group_id = %s
                """
                db.execute(sql, (group_name, group_function, group_id))
                affected_rows = db.cursor.rowcount
                if affected_rows > 0:
                    logger.info(f"更新群聊信息: {group_id} - {group_name}")
                    return True
                else:
                    logger.info(f"未找到群聊信息: {group_id}")
                    return False
        except Exception as e:
            logger.error(f"更新群聊信息失败: {e}")
            return False
    
    def remove_group(self, group_id: str) -> bool:
        """删除群聊信息"""
        try:
            with get_bot_db_connection() as db:
                sql = f"DELETE FROM {self.table_name} WHERE group_id = %s"
                db.execute(sql, (group_id,))
                affected_rows = db.cursor.rowcount
                if affected_rows > 0:
                    logger.info(f"删除群聊信息: {group_id}")
                    return True
                else:
                    logger.info(f"未找到群聊信息: {group_id}")
                    return False
        except Exception as e:
            logger.error(f"删除群聊信息失败: {e}")
            return False
    
    def list_groups(self) -> List[Dict[str, Any]]:
        """列出所有群聊信息"""
        try:
            with get_bot_db_connection() as db:
                sql = f"""
                SELECT group_id, group_name, group_function, created_at, updated_at 
                FROM {self.table_name} 
                ORDER BY updated_at DESC
                """
                cursor = db.execute(sql)
                results = cursor.fetchall()
                logger.info(f"获取群聊列表，共 {len(results)} 条记录")
                return results
        except Exception as e:
            logger.error(f"获取群聊列表失败: {e}")
            return []
    
    def get_group_by_id(self, group_id: str) -> Optional[Dict[str, Any]]:
        """根据群号获取群聊信息"""
        try:
            with get_bot_db_connection() as db:
                sql = f"""
                SELECT group_id, group_name, group_function, created_at, updated_at 
                FROM {self.table_name} 
                WHERE group_id = %s
                """
                cursor = db.execute(sql, (group_id,))
                result = cursor.fetchone()
                return result
        except Exception as e:
            logger.error(f"获取群聊信息失败: {e}")
            return None


# 创建数据库管理器实例
db_manager = DatabaseManager()


# dao/message_dao.py
from nonebot import logger
from typing import List, Dict
from contextlib import contextmanager

from mysql.connector import Error
import json

from ...common import get_diting_db_connection


class MessageDAO:
    """
    消息数据访问对象（DAO），用于操作 messages_event_logs 表
    """

    # @staticmethod
    # def create_table():
    #     """创建表（首次运行时调用）"""
    #     create_table_sql = """
    #     CREATE TABLE IF NOT EXISTS messages_event_logs (
    #         id BIGINT AUTO_INCREMENT PRIMARY KEY,
    #         message_id INT NOT NULL UNIQUE,
    #         self_id BIGINT NOT NULL,
    #         user_id BIGINT NOT NULL,
    #         message_type VARCHAR(10) NOT NULL,
    #         group_id BIGINT DEFAULT NULL,
    #         sub_type VARCHAR(20) NOT NULL,
    #         post_type VARCHAR(20) NOT NULL DEFAULT 'message',
    #         time INT NOT NULL,
    #         raw_message TEXT NOT NULL,
    #         message_json JSON NOT NULL,
    #         to_me BOOLEAN NOT NULL DEFAULT FALSE,
    #         reply_json JSON DEFAULT NULL,
    #         sender_nickname VARCHAR(100) NOT NULL,
    #         sender_card VARCHAR(100) DEFAULT NULL,
    #         sender_sex ENUM('male', 'female', 'unknown') DEFAULT 'unknown',
    #         sender_age TINYINT DEFAULT NULL,
    #         sender_role ENUM('owner', 'admin', 'member') DEFAULT 'member',
    #         anonymous_flag VARCHAR(100) DEFAULT NULL,
    #         anonymous_name VARCHAR(50) DEFAULT NULL,
    #         anonymous_id INT DEFAULT NULL,
    #         created_at DATETIME(6) DEFAULT CURRENT_TIMESTAMP(6),
    #         updated_at DATETIME(6) DEFAULT CURRENT_TIMESTAMP(6) ON UPDATE CURRENT_TIMESTAMP(6),

    #         INDEX idx_user_id (user_id),
    #         INDEX idx_group_id (group_id),
    #         INDEX idx_time (time),
    #         INDEX idx_to_me (to_me),
    #         INDEX idx_type_group (message_type, group_id),
    #         INDEX idx_created_at (created_at),
    #         INDEX idx_raw_message (raw_message(100))
    #     ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
    #     """
    #     try:
    #         with get_diting_db_connection() as conn:
    #             conn.execute(create_table_sql)
    #         logger.info("表 `messages_event_logs` 创建/检查完成")
    #     except Error as e:
    #         logger.error(f"创建表 messages_event_logs 失败: {e}")
    #         raise

    @staticmethod
    def save_message(event_data: Dict) -> bool:
        """
        保存一条消息事件
        :param event_data: 从 MessageEvent.dict() 得到的数据
        :return: 是否成功
        """
        insert_sql = """
        INSERT INTO messages_event_logs (
            message_id, self_id, user_id, message_type, group_id, sub_type,
            post_type, time, raw_message, message_json, to_me, reply_json,
            sender_nickname, sender_card, sender_sex, sender_age, sender_role,
            anonymous_flag, anonymous_name, anonymous_id
        ) VALUES (
            %(message_id)s, %(self_id)s, %(user_id)s, %(message_type)s, %(group_id)s, %(sub_type)s,
            %(post_type)s, %(time)s, %(raw_message)s, %(message_json)s, %(to_me)s, %(reply_json)s,
            %(sender_nickname)s, %(sender_card)s, %(sender_sex)s, %(sender_age)s, %(sender_role)s,
            %(anonymous_flag)s, %(anonymous_name)s, %(anonymous_id)s
        ) ON DUPLICATE KEY UPDATE 
            updated_at = CURRENT_TIMESTAMP(6)
        """

        params = MessageDAO._extract_params(event_data)

        try:
            with get_diting_db_connection() as conn:
                conn.execute(insert_sql, params)
            return True
        except Error as e:
            logger.error(f"保存消息失败 (message_id={event_data.get('message_id')}): {e}")
            return False

    @staticmethod
    def _extract_params(event_data: Dict) -> Dict:
        """从 event 数据中提取插入参数"""
        sender = event_data.get("sender", {}) or {}
        anonymous = event_data.get("anonymous", {}) or {}

        message_json_str = json.dumps(
            event_data["message"], 
            ensure_ascii=False, 
            default=str  # 防止无法序列化的对象报错
        )

        reply_json_str = None
        if event_data.get("reply"):
            reply_json_str = json.dumps(
                event_data["reply"], 
                ensure_ascii=False, 
                default=str
        )
            
        return {
            "message_id": event_data["message_id"],
            "self_id": event_data["self_id"],
            "user_id": event_data["user_id"],
            "message_type": event_data["message_type"],
            "group_id": event_data.get("group_id"),
            "sub_type": event_data["sub_type"],
            "post_type": event_data["post_type"],
            "time": event_data["time"],
            "raw_message": event_data["raw_message"],
            "message_json": message_json_str,
            "to_me": event_data["to_me"],
            "reply_json": reply_json_str,

            # sender 字段
            "sender_nickname": sender.get("nickname", ""),
            "sender_card": sender.get("card"),
            "sender_sex": sender.get("sex", "unknown"),
            "sender_age": sender.get("age"),
            "sender_role": sender.get("role", "member"),

            # anonymous 字段
            "anonymous_flag": anonymous.get("flag"),
            "anonymous_name": anonymous.get("name"),
            "anonymous_id": anonymous.get("id"),
        }

    @staticmethod
    def get_recent_messages(limit: int = 100) -> List[Dict]:
        """获取最近 N 条消息"""
        sql = """
        SELECT message_id, user_id, group_id, raw_message, time, sender_nickname, sender_card
        FROM messages_event_logs
        ORDER BY time DESC
        LIMIT %s
        """
        try:
            with get_diting_db_connection() as conn:
                cursor = conn.execute(sql, (limit,))
                return cursor.fetchall()
        except Error as e:
            logger.error(f"查询最近消息失败: {e}")
            return []

    @staticmethod
    def search_messages_by_keyword(keyword: str, limit: int = 50) -> List[Dict]:
        """根据关键词模糊搜索消息"""
        sql = """
        SELECT message_id, user_id, group_id, raw_message, time, sender_nickname
        FROM messages_event_logs
        WHERE raw_message LIKE %s
        ORDER BY time DESC
        LIMIT %s
        """
        try:
            with get_diting_db_connection() as conn:
                cursor = conn.execute(sql, (f"%{keyword}%", limit))
                return cursor.fetchall()
        except Error as e:
            logger.error(f"搜索消息失败 (keyword={keyword}): {e}")
            return []
        

message_dao = MessageDAO()
# message_dao.create_table()
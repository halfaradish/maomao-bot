"""
Todo提醒插件配置
"""

from pydantic import BaseModel
from typing import Dict, Any, Optional
import os


class Config(BaseModel):
    """插件配置类"""
    
    # 数据库配置
    database_config: Dict[str, Any] = {
        "host": os.getenv("BOT_DB_HOST", "localhost"),
        "user": os.getenv("BOT_DB_USER", "gxuicpc"),
        "password": os.getenv("BOT_DB_PASSWORD", ""),
        "database": os.getenv("BOT_DB_NAME", "diting_qq_bot"),
        "port": int(os.getenv("BOT_DB_PORT", "3307")),
        "pool_size": int(os.getenv("BOT_DB_POOL_SIZE", "20"))
    }
    
    # 提醒配置
    reminder_config: Dict[str, Any] = {
        "check_interval": 60,  # 检查间隔(秒)
        "max_reminders_per_user": 10,  # 每用户最大提醒数
        "max_reminders_per_group": 50,  # 每群组最大提醒数
        "cleanup_completed_days": 30,  # 清理已完成提醒的天数
        "retry_failed_reminders": True,  # 是否重试失败的提醒
        "max_retry_attempts": 3,  # 最大重试次数
    }
    
    # 时间解析配置
    time_parser_config: Dict[str, Any] = {
        "default_timezone": "Asia/Shanghai",
        "supported_formats": [
            "明天{hour}点",
            "后天{hour}点",
            "{hours}小时{minutes}分钟后",
            "{minutes}分钟后",
            "{hours}小时后",
            "{days}天后",
            "{year}-{month}-{day} {hour}:{minute}",
            "每天{hour}点",
            "工作日{hour}点",
            "每周{weekday}{hour}点"
        ]
    }
    
    # 消息配置
    message_config: Dict[str, Any] = {
        "reminder_template": "提醒通知\n时间：{remind_time}\n内容：{content}\n创建者：{created_by}",
        "success_template": "{action}成功！",
        "error_template": "{action}失败：{error}",
        "list_template": "{title}:\n{items}",
        "help_template": "帮助信息:\n{help_text}"
    }
    
    # 权限配置
    permission_config: Dict[str, Any] = {
        "allow_private_reminders": True,
        "allow_group_reminders": True,
        "allow_user_mentions": True,
        "require_admin_for_group_reminders": False,
        "allow_cross_group_reminders": False
    }
    
    
    def get_database_config(self) -> Dict[str, Any]:
        """获取数据库配置"""
        return self.database_config
    
    def get_reminder_config(self) -> Dict[str, Any]:
        """获取提醒配置"""
        return self.reminder_config
    
    def get_time_parser_config(self) -> Dict[str, Any]:
        """获取时间解析配置"""
        return self.time_parser_config
    
    def get_message_config(self) -> Dict[str, Any]:
        """获取消息配置"""
        return self.message_config
    
    def get_permission_config(self) -> Dict[str, Any]:
        """获取权限配置"""
        return self.permission_config
    

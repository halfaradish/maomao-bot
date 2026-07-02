from nonebot import logger
import os
from dotenv import load_dotenv

load_dotenv()

environment: str = os.getenv('ENVIRONMENT') or 'prod'

_env_file = f".env.{environment}"

if os.path.exists(_env_file):
    load_dotenv(_env_file)
    logger.info(f"successful load {_env_file}")
else:
    logger.error(f"{_env_file} not found. Falling back to default or system env.")

class Config:
    HOST: str = os.getenv('HOST') or "0.0.0.0"
    PORT: str = os.getenv('PORT') or "6090"

class IcpcDBConfig:
    ICPC_DB_HOST: str = os.getenv('ICPC_DB_HOST') or 'localhost'
    ICPC_DB_USER: str = os.getenv('ICPC_DB_USER') or 'root'
    ICPC_DB_PASSWORD: str = os.getenv('ICPC_DB_PASSWORD') or ''
    ICPC_DB_NAME: str = os.getenv('ICPC_DB_NAME') or ''
    ICPC_DB_PORT: int = int(os.getenv('ICPC_DB_PORT') or 3306)
    ICPC_DB_POOL_SIZE: int = int(os.getenv('ICPC_DB_POOL_SIZE') or 20)

class DiTingBotDBConfig:
    BOT_DB_HOST: str = os.getenv('BOT_DB_HOST') or 'localhost'
    BOT_DB_USER: str = os.getenv('BOT_DB_USER') or 'root'
    BOT_DB_PASSWORD: str = os.getenv('BOT_DB_PASSWORD') or ''
    BOT_DB_NAME: str = os.getenv('BOT_DB_NAME') or ''
    BOT_DB_PORT: int = int(os.getenv('BOT_DB_PORT') or 3306)
    BOT_DB_POOL_SIZE: int = int(os.getenv('BOT_DB_POOL_SIZE') or 20)

class CheckUpDay:
    # check_up_enable
    CHECK_UP_ENABLE: bool = bool(os.getenv('CHECK_UP_ENABLE') or False)
    # 表示第一天的八点
    DAY_START: int = int(os.getenv('DAY_START') or 8)
    # 表示第二天的两点
    DAY_END: int = int(os.getenv('DAY_END') or 2)
    # 定时发送的时间
    TIMING_HOUR: str = str(os.getenv('TIMING_HOUR', 10))
    TIMING_MINUTE: str = str(os.getenv('TIMING_MINUTE', 30))
    TIMING_SECOND: str = str(os.getenv('TIMING_SECOND', 00))

class SleepConfig:
    # 是否启动延迟回复（处理布尔值：环境变量设为"False"或"0"时为False，否则用默认值True）
    delay_env = os.getenv('DELAY_ENABLED')
    DELAY_ENABLED: bool = False if delay_env in ("False", "0") else (True if delay_env else True)
    # 最短睡眠时间（转换为float，默认0.3）
    MIN_SLEEP_TIME: float = float(os.getenv('MIN_SLEEP_TIME', 0.3))
    # 最长睡眠时间（转换为float，默认1.0）
    MAX_SLEEP_TIME: float = float(os.getenv('MAX_SLEEP_TIME', 1.0))

class QQControlConfig:
    # QQ控制的主机地址
    QQ_CONTROL_HOST: str = os.getenv('QQ_CONTROL_HOST') or 'localhost'
    # QQ控制的端口
    QQ_CONTROL_PORT: int = int(os.getenv('QQ_CONTROL_PORT') or 6097)
    # QQ控制的令牌
    QQ_CONTROL_TOKEN: str = os.getenv('QQ_CONTROL_TOKEN') or 'default_token'

class DiTingData:
    NONEBOT_DATA_DIR: str = os.getenv('NONEBOT_DATA_DIR') or '/app/data'
    DATA_DIR: str = os.getenv('DATA_DIR') or "/app/data"
    IMAGES_DIR: str = os.getenv('IMAGES_DIR') or "/app/data/tmp/"
    IMAGES_COMPRESSED_DIR: str = os.getenv('IMAGES_COMPRESSED_DIR') or "/app/data/pictures"
    # 过题排行数据存放目录
    SUB_RANKING_DIR: str = os.getenv('SUB_RANKING_DIR') or "/app/data/sub_ranking"
    # sql语句存放目录
    SQL_DIR: str = os.getenv('SQL_DIR') or "/app/data/sql"

class RedisConfig:
    HOST: str = os.getenv('NEW_OJ_REDIS_HOST') or 'localhost'
    PORT: int = int(os.getenv('NEW_OJ_REDIS_PORT') or 6379)
    PASSWORD: str = os.getenv('NEW_OJ_REDIS_PASSWORD') or '123456'
    DB: int = int(os.getenv('NEW_OJ_REDIS_DB') or 0)
    MAX_CONNECTIONS: int = int(os.getenv('NEW_OJ_REDIS_MAX_CONNECTIONS') or 20)
    SOCKET_TIMEOUT: int = int(os.getenv('NEW_OJ_REDIS_SOCKET_timeout') or 5)
    SOCKET_CONNECT_TIMEOUT: int = int(os.getenv('NEW_OJ_REDIS_SOCKET_CONNECT_TIMEOUT') or 5)
    DECODE_RESPONSES: bool = bool(os.getenv('NEW_OJ_REDIS_DECODE_RESPONSES') or True)
    RETRY_ON_TIME: bool = bool(os.getenv('NEW_OJ_REDIS_RETRY_ON_TIME') or True)
    HEALTH_CHECK_INTERVAL: int = int(os.getenv('NEW_OJ_REDIS_HEALTH_CHECK_INTERVAL') or 30)

class NoneBotToken:
    ONEBOT_ACCESS_TOKEN: str = str(os.getenv('ONEBOT_ACCESS_TOKEN') or '')
    DITING_API_ACCESS_TOKEN: str = str(os.getenv('DITING_API_ACCESS_TOKEN') or '')

class SiqiAuthConfig:
    """司契权限系统配置"""
    HOST: str = os.getenv('SIQI_AUTH_HOST') or 'localhost'
    PORT: int = int(os.getenv('SIQI_AUTH_PORT') or 8001)
    APP_CODE: str = os.getenv('SIQI_AUTH_APP_CODE') or 'qq_bot'
    TIMEOUT: int = int(os.getenv('SIQI_AUTH_TIMEOUT') or 2)
    _enabled_env = os.getenv('SIQI_AUTH_ENABLED')
    ENABLED: bool = False if _enabled_env in ("False", "false", "0") else (True if _enabled_env else True)

class LogConfig:
    """文件日志记录配置（用于 logger.add()）"""
    LOG_FILE_PATH: str = os.getenv('LOG_FILE_PATH') or "logs/nonebot.log"
    LOG_FILE_ROTATION: str = os.getenv('LOG_FILE_ROTATION') or "00:00"
    LOG_FILE_RETENTION: str = os.getenv('LOG_FILE_RETENTION') or "7 days"
    LOG_FILE_LEVEL: str = os.getenv('LOG_FILE_LEVEL') or "DEBUG"
    LOG_FILE_ENCODING: str = os.getenv('LOG_FILE_ENCODING') or "utf-8"
    _enqueue_env = os.getenv('LOG_FILE_ENQUEUE')
    LOG_FILE_ENQUEUE: bool = False if _enqueue_env in ("False", "false", "0") else (True if _enqueue_env else True)
    LOG_FILE_COMPRESSION: str = os.getenv('LOG_FILE_COMPRESSION') or "zip"

class WebUIConfig:
    """Web管理面板JWT配置"""
    WEBUI_JWT_SECRET: str = os.getenv('WEBUI_JWT_SECRET') or ''
    WEBUI_DEV_PASSWORD: str = os.getenv('WEBUI_DEV_PASSWORD') or ''
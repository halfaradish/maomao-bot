from nonebot import logger
import os
from dotenv import load_dotenv

load_dotenv()

# 未设 ENVIRONMENT 时回退 dev（fail-safe）：独立脚本/临时进程不应误用 prod 配置与 prod 数据空间
environment: str = os.getenv('ENVIRONMENT') or 'dev'

_env_file = f".env.{environment}"

if os.path.exists(_env_file):
    load_dotenv(_env_file)
    logger.info(f"successful load {_env_file}")
else:
    logger.error(f"{_env_file} not found. Falling back to default or system env.")

def _env_bool(name: str, default: bool) -> bool:
    """解析布尔环境变量：0/false/no/off（不区分大小写）为 False，
    其余非空值为 True，未设置或空值时取 default。"""
    val = os.getenv(name)
    if val is None or val.strip() == '':
        return default
    return val.strip().lower() not in ('0', 'false', 'no', 'off')

class Config:
    HOST: str = os.getenv('HOST') or "0.0.0.0"
    PORT: str = os.getenv('PORT') or "6090"

class IcpcDBConfig:
    ICPC_DB_HOST: str = os.getenv('ICPC_DB_HOST') or 'host.docker.internal'
    ICPC_DB_USER: str = os.getenv('ICPC_DB_USER') or 'root'
    ICPC_DB_PASSWORD: str = os.getenv('ICPC_DB_PASSWORD') or ''
    ICPC_DB_NAME: str = os.getenv('ICPC_DB_NAME') or ''
    ICPC_DB_PORT: int = int(os.getenv('ICPC_DB_PORT') or 3307)
    ICPC_DB_POOL_SIZE: int = int(os.getenv('ICPC_DB_POOL_SIZE') or 20)

class DiTingBotDBConfig:
    BOT_DB_HOST: str = os.getenv('BOT_DB_HOST') or 'host.docker.internal'
    BOT_DB_USER: str = os.getenv('BOT_DB_USER') or 'root'
    BOT_DB_PASSWORD: str = os.getenv('BOT_DB_PASSWORD') or ''
    BOT_DB_NAME: str = os.getenv('BOT_DB_NAME') or ''
    BOT_DB_PORT: int = int(os.getenv('BOT_DB_PORT') or 3307)
    BOT_DB_POOL_SIZE: int = int(os.getenv('BOT_DB_POOL_SIZE') or 20)

class CheckUpDay:
    # check_up_enable
    CHECK_UP_ENABLE: bool = _env_bool('CHECK_UP_ENABLE', False)
    # 表示第一天的八点
    DAY_START: int = int(os.getenv('DAY_START') or 8)
    # 表示第二天的两点
    DAY_END: int = int(os.getenv('DAY_END') or 2)
    # 定时发送的时间
    TIMING_HOUR: str = str(os.getenv('TIMING_HOUR', 10))
    TIMING_MINUTE: str = str(os.getenv('TIMING_MINUTE', 30))
    TIMING_SECOND: str = str(os.getenv('TIMING_SECOND', 00))

class SleepConfig:
    # 是否启动延迟回复
    DELAY_ENABLED: bool = _env_bool('DELAY_ENABLED', True)
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
    SOCKET_TIMEOUT: int = int(os.getenv('NEW_OJ_REDIS_SOCKET_TIMEOUT') or os.getenv('NEW_OJ_REDIS_SOCKET_timeout') or 5)
    SOCKET_CONNECT_TIMEOUT: int = int(os.getenv('NEW_OJ_REDIS_SOCKET_CONNECT_TIMEOUT') or 5)
    DECODE_RESPONSES: bool = _env_bool('NEW_OJ_REDIS_DECODE_RESPONSES', True)
    RETRY_ON_TIME: bool = _env_bool('NEW_OJ_REDIS_RETRY_ON_TIME', True)
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
    ENABLED: bool = _env_bool('SIQI_AUTH_ENABLED', True)

class LogConfig:
    """文件日志记录配置（用于 logger.add()）"""
    LOG_FILE_PATH: str = os.getenv('LOG_FILE_PATH') or "logs/nonebot.log"
    LOG_FILE_ROTATION: str = os.getenv('LOG_FILE_ROTATION') or "00:00"
    LOG_FILE_RETENTION: str = os.getenv('LOG_FILE_RETENTION') or "7 days"
    LOG_FILE_LEVEL: str = os.getenv('LOG_FILE_LEVEL') or "DEBUG"
    LOG_FILE_ENCODING: str = os.getenv('LOG_FILE_ENCODING') or "utf-8"
    LOG_FILE_ENQUEUE: bool = _env_bool('LOG_FILE_ENQUEUE', True)
    LOG_FILE_COMPRESSION: str = os.getenv('LOG_FILE_COMPRESSION') or "zip"

class WebUIConfig:
    """Web管理面板JWT配置"""
    WEBUI_JWT_SECRET: str = os.getenv('WEBUI_JWT_SECRET') or ''
    WEBUI_DEV_PASSWORD: str = os.getenv('WEBUI_DEV_PASSWORD') or ''
import os
from dotenv import load_dotenv

load_dotenv()

class Config:
    HOST: str = os.getenv('HOST')
    PORT: str = os.getenv('PORT')

class IcpcDBConfig:
    ICPC_DB_HOST: str = os.getenv('ICPC_DB_HOST') or 'localhost'
    ICPC_DB_USER: str = os.getenv('ICPC_DB_USER') or 'root'
    ICPC_DB_PASSWORD: str = os.getenv('ICPC_DB_PASSWORD') or ''
    ICPC_DB_NAME: str = os.getenv('ICPC_DB_NAME') or ''
    ICPC_DB_PORT: int = os.getenv('ICPC_DB_PORT') or 3306
    ICPC_DB_POOL_SIZE: int = os.getenv('ICPC_DB_POOL_SIZE') or 20

class DiTingBotDBConfig:
    BOT_DB_HOST: str = os.getenv('BOT_DB_HOST') or 'localhost'
    BOT_DB_USER: str = os.getenv('BOT_DB_USER') or 'root'
    BOT_DB_PASSWORD: str = os.getenv('BOT_DB_PASSWORD') or ''
    BOT_DB_NAME: str = os.getenv('BOT_DB_NAME') or ''
    BOT_DB_PORT: int = os.getenv('BOT_DB_PORT') or 3306
    BOT_DB_POOL_SIZE: int = os.getenv('BOT_DB_POOL_SIZE') or 50

class CheckUpDay:
    # 表示第一天的八点
    DAY_START: int = int(os.getenv('DAY_START') or 8)
    # 表示第二天的两点
    DAY_END: int = int(os.getenv('DAY_END') or 2)
    # 定时发送的时间
    TIMING_HOUR: str = str(os.getenv('TIMING_HOUR', 10))
    TIMING_MINUTE: str = str(os.getenv('TIMING_MINUTE', 30))
    TIMING_SECOND: str = str(os.getenv('TIMING_SECOND', 00))

class SleepConfig:
    # 最短睡眠时间
    MIN_SLEEP_TIME: float = os.getenv('MIN_SLEEP_TIME') or 0.3
    # 最长睡眠时间
    MAX_SLEEP_TIME: float = os.getenv('MAX_SLEEP_TIME') or 1.0

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
    PORT: int = os.getenv('NEW_OJ_REDIS_PORT') or 6379
    PASSWORD: str = os.getenv('NEW_OJ_REDIS_PASSWORD') or '123456'
    DB: int = os.getenv('NEW_OJ_REDIS_DB') or 0
    MAX_CONNECTIONS: int = os.getenv('NEW_OJ_REDIS_MAX_CONNECTIONS') or 20
    SOCKET_timeout: int = os.getenv('NEW_OJ_REDIS_SOCKET_timeout') or 5
    SOCKET_CONNECT_TIMEOUT: int = os.getenv('NEW_OJ_REDIS_SOCKET_CONNECT_TIMEOUT') or 5
    DECODE_RESPONSES: int = os.getenv('NEW_OJ_REDIS_DECODE_RESPONSES') or True
import os
from datetime import datetime
from dotenv import load_dotenv

load_dotenv()

class Config:
    HOST = os.getenv('HOST')
    PORT = os.getenv('PORT')

class IcpcDBConfig:
    ICPC_DB_HOST = os.getenv('ICPC_DB_HOST') or 'localhost'
    ICPC_DB_USER = os.getenv('ICPC_DB_USER') or 'root'
    ICPC_DB_PASSWORD = os.getenv('ICPC_DB_PASSWORD') or ''
    ICPC_DB_NAME = os.getenv('ICPC_DB_NAME') or ''
    ICPC_DB_PORT = os.getenv('ICPC_DB_PORT') or 3306


class CheckUpDay:
    DAY_START = int(os.getenv('DAY_START') or 8) # 表示第一天的八点
    DAY_END = int(os.getenv('DAY_END') or 2) # 表示第二天的两点

from sqlalchemy import create_engine
from sqlalchemy.ext.automap import automap_base
from sqlalchemy.orm import sessionmaker
import os

# ========== 从环境变量读取，和 Django 保持一致 ==========
DB_CONFIG = {
    'user': os.getenv('BOT_DB_USER', 'root'),
    'password': os.getenv('BOT_DB_PASSWORD', '123456'),
    'host': os.getenv('BOT_DB_HOST', 'localhost'),
    'port': int(os.getenv('BOT_DB_PORT', '3306')),
    'database': os.getenv('BOT_DB_NAME', 'diting_qq_bot')
}

# ========== MySQL 连接 ==========
engine = create_engine(
    f"mysql+pymysql://{DB_CONFIG['user']}:{DB_CONFIG['password']}"
    f"@{DB_CONFIG['host']}:{DB_CONFIG['port']}/{DB_CONFIG['database']}"
    f"?charset=utf8mb4",
    echo=False,
    pool_pre_ping=True,
    pool_recycle=3600
)

# ========== 反射：自动读取 Django 的表 ==========
Base = automap_base()
Base.prepare(autoload_with=engine)

# 获取映射类（表名必须和 Django 一致）
MonitoredGroup = Base.classes.monitored_groups
GroupFile = Base.classes.group_files

Session = sessionmaker(bind=engine)
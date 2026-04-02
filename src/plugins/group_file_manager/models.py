from sqlalchemy import create_engine, Column, Integer, String, DateTime, BigInteger, UniqueConstraint
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker
from datetime import datetime

Base = declarative_base()

class MonitoredGroup(Base):
    """监控的QQ群"""
    __tablename__ = "monitored_groups"
    
    id = Column(Integer, primary_key=True)
    group_id = Column(BigInteger, unique=True, nullable=False, comment="QQ群号")
    group_name = Column(String(255), comment="群名称")
    created_at = Column(DateTime, default=datetime.now)
    is_active = Column(Integer, default=1, comment="是否启用监控")

class GroupFile(Base):
    """群文件记录"""
    __tablename__ = "group_files"
    
    id = Column(Integer, primary_key=True)
    group_id = Column(BigInteger, nullable=False, comment="QQ群号")
    file_id = Column(String(255), nullable=False, comment="文件ID（去重标识）")
    file_name = Column(String(500), nullable=False, comment="文件名")
    file_size = Column(BigInteger, comment="文件大小")
    file_path = Column(String(1000), comment="本地存储路径")
    uploader_id = Column(BigInteger, comment="上传者QQ")
    uploader_name = Column(String(255), comment="上传者昵称")
    upload_time = Column(DateTime, comment="原始上传时间")
    downloaded_at = Column(DateTime, default=datetime.now, comment="下载时间")
    
    # 去重：同一文件在不同群只存一次
    file_hash = Column(String(64), comment="文件MD5哈希")
    
    __table_args__ = (
        UniqueConstraint('file_hash', name='unique_file_hash'),  # 文件级别去重
    )

# 数据库连接
engine = create_engine('sqlite:///group_files.db', echo=False)
Base.metadata.create_all(engine)
Session = sessionmaker(bind=engine)
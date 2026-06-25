"""
群统计插件数据库操作类（SQLAlchemy 异步实现）
"""
import logging
from typing import Dict, List, Optional, Any

from nonebot import logger
from sqlalchemy import select

from ...common.database import async_session_factory
from ...common.models.botdb_models import GroupStatistic


class DatabaseManager:
    """数据库管理类，处理群统计相关的数据库操作"""

    def __init__(self):
        self.table_name = "group_statistics"

    async def add_group(self, group_id: str, group_name: str, group_function: str) -> bool:
        """添加群聊信息（group_id 重复时返回 False）"""
        try:
            async with async_session_factory() as session:
                obj = GroupStatistic(
                    group_id=group_id,
                    group_name=group_name,
                    group_function=group_function,
                )
                session.add(obj)
                await session.commit()
                logger.info(f"添加群聊信息: {group_id} - {group_name}")
                return True
        except Exception as e:
            logger.info(f"群聊信息已存在: {group_id} ({e})")
            return False

    async def update_group(self, group_id: str, group_name: str, group_function: str) -> bool:
        """更新群聊信息"""
        try:
            async with async_session_factory() as session:
                stmt = select(GroupStatistic).where(GroupStatistic.group_id == group_id)
                result = await session.execute(stmt)
                group = result.scalars().first()
                if group:
                    group.group_name = group_name
                    group.group_function = group_function
                    await session.commit()
                    logger.info(f"更新群聊信息: {group_id} - {group_name}")
                    return True
                else:
                    logger.info(f"未找到群聊信息: {group_id}")
                    return False
        except Exception as e:
            logger.error(f"更新群聊信息失败: {e}")
            return False

    async def remove_group(self, group_id: str) -> bool:
        """删除群聊信息"""
        try:
            async with async_session_factory() as session:
                stmt = select(GroupStatistic).where(GroupStatistic.group_id == group_id)
                result = await session.execute(stmt)
                group = result.scalars().first()
                if group:
                    await session.delete(group)
                    await session.commit()
                    logger.info(f"删除群聊信息: {group_id}")
                    return True
                else:
                    logger.info(f"未找到群聊信息: {group_id}")
                    return False
        except Exception as e:
            logger.error(f"删除群聊信息失败: {e}")
            return False

    async def list_groups(self) -> List[Dict[str, Any]]:
        """列出所有群聊信息"""
        try:
            async with async_session_factory() as session:
                stmt = select(GroupStatistic).order_by(GroupStatistic.updated_at.desc())
                result = await session.execute(stmt)
                groups = result.scalars().all()
                return [
                    {
                        "group_id": g.group_id,
                        "group_name": g.group_name,
                        "group_function": g.group_function,
                        "created_at": g.created_at,
                        "updated_at": g.updated_at,
                    }
                    for g in groups
                ]
        except Exception as e:
            logger.error(f"获取群聊列表失败: {e}")
            return []

    async def get_group_by_id(self, group_id: str) -> Optional[Dict[str, Any]]:
        """根据群号获取群聊信息"""
        try:
            async with async_session_factory() as session:
                stmt = select(GroupStatistic).where(GroupStatistic.group_id == group_id)
                result = await session.execute(stmt)
                group = result.scalars().first()
                if group:
                    return {
                        "group_id": group.group_id,
                        "group_name": group.group_name,
                        "group_function": group.group_function,
                        "created_at": group.created_at,
                        "updated_at": group.updated_at,
                    }
                return None
        except Exception as e:
            logger.error(f"获取群聊信息失败: {e}")
            return None


# 创建数据库管理器实例
db_manager = DatabaseManager()

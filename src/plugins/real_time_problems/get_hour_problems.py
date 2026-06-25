from nonebot import (
    logger,
    get_plugin_config
)

from datetime import datetime

from .config import Config
from ...common import get_icpc_db_connection, utils

config = get_plugin_config(Config)

class HourSubCondition:
    """
    查询范围内的过题数据
    """

    @classmethod
    async def get_hour_sub_records(cls, start_time: datetime, end_time: datetime):
        """
        根据传入的start_time和end_time查询数据
        """
        query = utils.GetSQL.read_sql_file(config.GET_HOUR_SUB_RECORDS)

        try:
            async with get_icpc_db_connection() as db:
                # 查询
                records = await db.execute(query, ([start_time, end_time] * 2))
                logger.info(records)
                return records
        except Exception as e:
            logger.error(f"查询数据库出错：{e}")
            return []
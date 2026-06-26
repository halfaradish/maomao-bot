from nonebot import(
    logger,
    get_plugin_config
)

from datetime import datetime, timedelta

from .config import Config
from ...common import get_icpc_db_connection, JsonUtils, utils

config = get_plugin_config(Config)

class DailySubCondition:
    """
    查询"当天"过题数据
    """

    @classmethod
    async def get_daily_sub_records(cls,
                              start_datetime: datetime,
                              end_datetime: datetime):
        """获取"每日"过题记录"""

        # 读取SQL语句
        query = utils.GetSQL.read_sql_file(config.GET_DAILY_SUB_RECORDS)

        # 获取前四年的范围
        time_ranges = []
        cur_year = start_datetime.year
        for year_offset in range(4):
            year = cur_year - year_offset
            past_star = start_datetime.replace(year=year)
            past_end = end_datetime.replace(year=year)
            time_ranges.extend([past_star, past_end])

        try:
            # 连接数据库
            async with get_icpc_db_connection() as db:
                # 查询数据
                records = await db.execute(query, (time_ranges * 2))
                return records
        except Exception as e:
            logger.error(f"查询数据库时出错：{e}")
            return []

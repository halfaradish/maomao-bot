from pydantic import BaseModel


class Config(BaseModel):
    """Plugin Config Here"""

    GET_HOUR_SUB_RECORDS: str = 'read/get_hour_sub_records.sql'

    target_groups: list = [
        "779245720"
    ]

    # 查询间隔时间
    check_gap_minutes: int = 10
from pydantic import BaseModel


class Config(BaseModel):
    """Plugin Config Here"""
    day_start_hour: int = 4

    data_filename: str = 'shadow_problem_view.json'

    GET_DAILY_SUB_RECORDS: str = 'read/get_daily_sub_records.sql'
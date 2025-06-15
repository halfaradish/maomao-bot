from pydantic import BaseModel


class Config(BaseModel):
    """Plugin Config Here"""
    # 延迟回复时间下限
    min_sleep_time: int = 1
    # 延迟回复时间上限
    max_sleep_time: int = 2
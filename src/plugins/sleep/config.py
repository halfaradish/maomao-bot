from pydantic import BaseModel

from ...config import SleepConfig

class Config(BaseModel):
    """Plugin Config Here"""
    # 延迟回复时间下限
    min_sleep_time: float = SleepConfig.MIN_SLEEP_TIME
    # 延迟回复时间上限
    max_sleep_time: float = SleepConfig.MAX_SLEEP_TIME
from pydantic import BaseModel
from typing import List


class Config(BaseModel):
    """Plugin Config Here"""
    # 要发送定时消息的群
    GROUP_IDS: List[int] = [779245720]
    # 定时发送的时间
    TIMING_HOUR: str = '02'
    TIMING_MINUTE: str = '00'
    TIMING_SECOND: str = '00'

    # 优先级
    priority: int = 10
    # 是否阻塞
    block: bool = True
from pydantic import BaseModel


class Config(BaseModel):
    """Plugin Config Here"""
    # 要发送定时消息的群
    GROUP_IDS = [779245720]
    # 定时发送的时间
    TIMING_HOUR = '02'
    TIMING_MINUTE = '00'
    TIMING_SECOND = '00'

    # 优先级
    priority = 10
    # 是否阻塞
    block = True
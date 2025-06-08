from pydantic import BaseModel
from typing import List


class Config(BaseModel):
    """Plugin Config Here"""
    # 优先级
    priority: int = 10
    # 是否阻塞
    block: bool = True

    # 要发送定时消息的群
    GROUP_IDS: List[int] = [779245720]
    # 定时发送的时间
    TIMING_HOUR: str = '02'
    TIMING_MINUTE: str = '00'
    TIMING_SECOND: str = '00'


    # /考勤 默认提示词
    DEFAULT_MSG: str = (
        "/考勤 命令使用方法\n"
        "[别名]\n"
        "/考勤状况; /check\n"
        "[参数]:\n"
        "日期(date): 起始日期, 格式(yyyy-mm-dd)\n"
        "范围(range): 展示从起始日期开始的之前x天的考勤范围\n"
        "[示例]:\n"
        "\"考勤 7\"-展示最近7天的考勤数据\n"
        "\"考勤 2025-6-8 3\"-展示从指定日期开始前3天的考勤数据"
    )
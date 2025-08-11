from pydantic import BaseModel
from typing import List

from ...config import CheckUpDay
from ...common import JsonUtils

class Config(BaseModel):
    """Plugin Config Here"""
    @staticmethod
    def load_json_to_group_id(filename: str = 'check_up.json') -> List[int]:
        content = []
        content, _=JsonUtils.read(filename, {"group_id": []})

        return content['group_id']

    # 优先级
    priority: int = 10
    # 是否阻塞
    block: bool = True

    # 考勤开始时间
    DAY_START: int = CheckUpDay.DAY_START
    # 考勤结束时间
    DAY_END: int = CheckUpDay.DAY_END

    # 要发送定时消息的群
    GROUP_IDS: List[int] = load_json_to_group_id()
    # 定时发送的时间
    TIMING_HOUR: str = CheckUpDay.TIMING_HOUR
    TIMING_MINUTE: str = CheckUpDay.TIMING_MINUTE
    TIMING_SECOND: str = CheckUpDay.TIMING_SECOND


    # /考勤 默认提示词
    DEFAULT_MSG: str = (
        "[考勤/考勤状况/check] 命令使用方法\n"
        "[参数]:\n"
        "日期(date): 起始日期, 格式(yyyy-mm-dd)\n"
        "范围(range): 展示从起始日期开始上溯x天的考勤范围\n"
        "[示例]:\n"
        "\"考勤 7\"-展示最近7天的考勤数据\n"
        "\"考勤 2025-6-8 3\"-展示从指定日期开始前3天的考勤数据"
    )

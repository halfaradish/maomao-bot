from pydantic import BaseModel
from typing import List


class Config(BaseModel):
    """
    比赛提醒插件配置类
    继承自Pydantic的BaseModel，用于自动从环境变量加载配置
    """

    # 是否启用比赛提醒功能
    clist_gci_enable: bool

    clist_schedule_job_enable: bool
    # 比赛提醒插件的优先级，数值越小优先级越高
    clist_gci_priority: int
    # 比赛提醒命令的触发关键词，默认为'比赛提醒'
    clist_gci_cmd: str = '比赛提醒'
    # 默认查询未来多少小时内的比赛
    clist_hours_ahead: int
    # 允许查询的最大小时数
    clist_max_hours_ahead: int
    # clist.by账号用户名
    clist_username: str
    # clist.by API密钥，用于访问比赛数据
    clist_api_key: str
    # clist.by API的基础URL
    clist_contest_fetch_base_url: str
    # 要查询的比赛平台列表
    clist_platforms: List[str]

    # 配置文件名
    clist_filename: str
    # 定时提醒每天的运行时间
    clist_remind_run_time_hour: int
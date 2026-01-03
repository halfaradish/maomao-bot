from pydantic import BaseModel


class Config(BaseModel):
    """Plugin Config Here"""
    ### in env ### 
    # 实时过题开关
    rtp_check_enable: bool = True
    # 实时过题播报开关
    rtp_report_enable: bool = True
    # 实时过题命令
    rtp_check_cmd: str = "实时过题"
    # 查询间隔时间
    rtp_check_gap_minutes: int = 60
    # 优先级
    rtp_check_priority: int = 20

    ### not in env ###
    GET_HOUR_SUB_RECORDS: str = 'read/get_hour_sub_records.sql'

    data_filename: str = 'real_time_problems.json'
from pydantic import BaseModel


class Config(BaseModel):
    """Plugin Config Here"""
    ### in env ###
    # 优先级
    sub_record_priority: int = 10
    # 是否阻塞
    sub_record_block: bool = True

    sub_record_roles_dict: dict = {
        "管理员": 0,
        "现役": 1,
        "退役": 2,
        "预备役": 3
    }
    # 角色词表（原 sub_records.json 的 roles_name，静态配置）
    sub_record_roles_name: list[str] = ["管理员", "现役", "退役", "预备役"]
    # 学校词表（原 sub_records.json 的 school，静态配置）
    sub_record_schools: list[str] = ["广西大学", "广西师范大学", "江西农业大学"]

    ### not in env ###
    scheduled_default_msg: str = "前 7 日没有过题数据"

    GET_RANGE_SUB_RECORDS: str = "read/sub_records_get_range_records.sql"

    sub_record_schedule_enable: bool = False

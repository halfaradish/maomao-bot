from pydantic import BaseModel


class Config(BaseModel):
    """Plugin Config Here"""
    # 响应优先级
    priority: int = 10
    # 是否阻塞
    block: bool = True

    user_msg: str = """/cmd 列出所有命令
    /赞我 点赞10次"""

    editor_msg: str = "/考勤 查看考勤情况(yyyy-mm-dd range)"

    admin_msg: str = ''
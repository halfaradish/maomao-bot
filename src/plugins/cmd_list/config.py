from pydantic import BaseModel


class Config(BaseModel):
    """Plugin Config Here"""
    # 响应优先级
    priority = 10
    # 是否阻塞
    block = True

    user_msg = """/cmd 列出所有命令
    /赞我 点赞10次"""

    editor_msg = "/考勤 查看考勤情况(yyyy-mm-dd range)"

    admin_msg = ''
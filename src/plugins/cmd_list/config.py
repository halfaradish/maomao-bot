from pydantic import BaseModel


class Config(BaseModel):
    """Plugin Config Here"""
    # 响应优先级
    priority: int = 10
    # 是否阻塞
    block: bool = True

    DEFAULT_MSG: str = (
        "/cmd: 列出所有命令\n"
        "[别名]\n"
        "/命令; /help; /帮助\n"
        "[命令列表]\n"
    )

    user_msg: list = [
        "/cmd 列出所有命令",
        "/赞我 点赞10次"
    ]

    editor_msg: list = [
        "/考勤 查看考勤情况"
    ]

    admin_msg: list = []
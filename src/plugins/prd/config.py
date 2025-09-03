from pydantic import BaseModel


class Config(BaseModel):
    """Plugin Config Here"""
    block: bool = True
    priority: int = 15

    data_filename: str = "prd.json"

    default_msg: str = (
        "[prd]命令使用详细\n"
        "[例子]:\n"
        "/prd ls (列出需求)\n"
        "/prd add 需求 (添加需求)\n"
        "/prd md 编号 修改后的内容 (修改需求)\n"
        "/prd rm 编号 (删除需求)\n"
        "/prd x 编号 (更改需求完成状态True-False)"
    )
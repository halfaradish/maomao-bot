from pydantic import BaseModel


class Config(BaseModel):
    """Plugin Config Here"""
    block: bool = True
    priority: int = 15

    data_filename: str = "prd.json"

    default_msg: str = (
        "[prd]命令使用详细\n"
        "[参数]:\n"
        "查(ls): 查看现有需求\n"
        "/prd ls *all(打*星号的为可选参数)\n"
        "增(add): 添加需求\n"
        "/prd add 需求\n"
        "改(md): 改动需求\n"
        "/prd md 编号 修改后的内容\n"
        "删(rm): 删除需求\n"
        "/prd rm 编号\n"
        "标记已完成(x): 标记需求已完成\n"
        "/prd x 编号"
    )
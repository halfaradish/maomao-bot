from pydantic import BaseModel
from typing import List

class Config(BaseModel):
    """Plugin Config Here"""
    priority: int = 10
    block: bool = True

    data_filename: str = 'shit_transport.json'

    DEFAULT_MSG = (
        "[搬史] 命令使用方法\n"
        "[示例]\n"
        "\"/搬史\" - 引用\回复 要搬的合并消息, 同时使用该命令, 即可将消息搬运到转发列表中的群组\n"
        "\"/搬史 list\" - 查看 '搬史小助手' 会转发哪些群组\n"
        "\"/搬史 add *group_id\" - 添加要转发的群组\n"
        "\"/搬史 rm *group_id\" - 删除转发列表中存在的群组"
    )
from pydantic import BaseModel
from typing import List

from ...config import QQControlConfig

class Config(BaseModel):
    """Plugin Config Here"""
    priority: int = 10
    block: bool = True

    data_filename: str = 'shit_transport.json'

    api_host: str = QQControlConfig.QQ_CONTROL_HOST
    api_port: int = QQControlConfig.QQ_CONTROL_PORT
    api_token: str = 'Bearer ' + QQControlConfig.QQ_CONTROL_TOKEN

    DEFAULT_MSG: str = (
        "[搬史] 命令使用方法\n"
        "[别名] 搬屎 转发 banshi bs\n"
        "[示例]\n"
        "\"/搬史\" - 引用\回复 要搬的合并消息, 同时使用该命令, 即可将消息搬运到转发列表中的群组\n"
        "\"/搬史 list\" - 查看 '搬史小助手' 会转发哪些群组\n"
        "\"/搬史 add *group_id\" - 添加要转发的群组\n"
        "\"/搬史 rm *group_id\" - 删除转发列表中存在的群组"
    )
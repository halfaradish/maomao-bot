from pydantic import BaseModel

class Config(BaseModel):
    """Plugin Config Here"""
    bs_priority: int = 10
    bs_block: bool = True

    bs_data_filename: str = 'shit_transport.json'

    banshi_frequency_statistics: str = "banshi_frequency_statistics"
    postshi_frequency_statistics: str = "postshi_frequency_statistics"

    bs_max_show_cnt: int = 5

    HELP_MSG: str = (
        "[搬史/搬屎/转发/banshi/bs] 命令使用方法\n"
        "[示例]\n"
        "\"/搬史\" - 引用\\回复 要搬的合并消息, 同时使用该命令, 即可将消息搬运到接收列表中的群组\n"
        "\"/搬史 list\" - 查看 '搬史小助手' 的群组配置\n"
        "\"/搬史 addpost *group_id\" - 添加可以发送bs命令的群组（仅超级管理员）\n"
        "\"/搬史 addreceive *group_id\" - 添加可以接收转发的群组（仅超级管理员）\n"
        "\"/搬史 rmpost *group_id\" - 移除可以发送bs命令的群组（仅超级管理员）\n"
        "\"/搬史 rmreceive *group_id\" - 移除可以接收转发的群组（仅超级管理员）\n"
        "\"/搬史 listpost\" - 查看可以发送bs命令的群组\n"
        "\"/搬史 listreceive\" - 查看可以接收转发的群组\n"
        "\"搬史 count\" - 搬史计数器"
    )
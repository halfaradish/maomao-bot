from pydantic import BaseModel


class Config(BaseModel):
    """群统计插件配置"""
    # 没有参数时的默认消息
    data_filename:str="group_statistics.json"
    DEFAULT_MSG: str = (
        "[群统计] 命令使用方法\n"
        "[功能]: 统计群聊信息并记录到数据库，支持添加、删除和查看群聊信息\n"
        "[格式]:\n"
        "群统计 add 群号 群名 群功能 - 添加群聊信息\n"
        "群统计 rm 群号 - 删除指定群聊信息\n"
        "群统计 ls - 查看所有群聊信息\n"
        "\n[示例]:\n"
        "群统计 add 10001 技术交流群 讨论编程技术\n"
        "群统计 rm 10001\n"
        "群统计 ls"
    )

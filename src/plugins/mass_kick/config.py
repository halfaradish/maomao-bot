from pydantic import BaseModel


class Config(BaseModel):
    """一键退群插件配置"""
    data_filename: str = "mass_kick.json"
    # 操作延迟（秒），避免触发频率限制
    operation_delay: float = 1.0
    # 日志群组ID列表（可选），用于记录操作日志
    log_group_ids: list = []
    
    # 没有参数时的默认消息
    DEFAULT_MSG: str = (
        "[一键退群] 命令使用方法\n"
        "[功能]: 批量将指定用户从所有管理的群组中踢出\n"
        "[权限]: 仅超级管理员可使用\n"
        "[格式]: 一键退群+QQ号\n"
        "[示例]:\n"
        "\"一键退群 123456789\" - 将QQ号为123456789的用户从所有管理的群组中踢出\n"
        "\n注意：此操作不可逆，请谨慎使用"
    )
    

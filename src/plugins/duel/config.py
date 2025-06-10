from pydantic import BaseModel


class Config(BaseModel):
    """Plugin Config Here"""
    # 优先级
    priority: int = 10
    # 是否阻塞
    block: bool = True

    # 没有参数时的默认消息, 
    DEFAULT_MSG: str = (
        "[duel/cf推题] 命令使用方法\n"
        "[使用示例]\n"
        "> /duel daily  每日推题(随机推送一题)\n"
    )

from pydantic import BaseModel


class Config(BaseModel):
    """
    分组发送插件配置
    """

    priority: int = 5
    block: bool = True
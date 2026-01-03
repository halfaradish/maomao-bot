from pydantic import BaseModel


class Config(BaseModel):
    """
    分组管理插件配置
    """

    command: str = "group"
    priority: int = 8
    block: bool = True
    max_members_preview: int = 50


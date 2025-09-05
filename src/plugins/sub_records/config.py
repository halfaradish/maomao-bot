from pydantic import BaseModel


class Config(BaseModel):
    """Plugin Config Here"""
    # 优先级
    priority: int = 10
    # 是否阻塞
    block: bool = True

    scheduled_default_msg: str = "前 7 日没有过题数据"
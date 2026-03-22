from pydantic import BaseModel


class Config(BaseModel):
    """Plugin Config Here"""
    # 优先级
    priority: int = 10
    # 是否阻塞
    block: bool = True
    like_time: int = 10

    like_auto_send_like: bool = False

    data_filename: str = "like.json"
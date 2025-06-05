from pydantic import BaseModel


class Config(BaseModel):
    """Plugin Config Here"""
    like_time = 10

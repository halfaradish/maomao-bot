from pydantic import BaseModel


class Config(BaseModel):
    """Plugin Config Here"""

    expire_time: int = 60
    max_request: int = 3
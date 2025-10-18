from pydantic import BaseModel


class Config(BaseModel):
    """Plugin Config Here"""
    priority: int = 10
    block: bool = True

    filename: str = 'spicy_pics.json'
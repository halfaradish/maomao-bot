from pydantic import BaseModel


class Config(BaseModel):
    """Plugin Config Here"""
    logging_info_priority: int = 114
    logging_info_block: bool = False
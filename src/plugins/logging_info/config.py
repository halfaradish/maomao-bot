import os
from pydantic import BaseModel


class Config(BaseModel):
    """Plugin Config Here"""
    logging_info_priority: int = 114
    logging_info_block: bool = False

    logging_info_enable: bool = os.getenv("LOGGING_INFO_ENABLE", "true").lower() in ("true", "1", "yes")
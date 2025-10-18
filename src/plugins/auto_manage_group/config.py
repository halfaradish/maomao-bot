from pydantic import BaseModel


class Config(BaseModel):
    """Plugin Config Here"""

    data_filename: str = "auto_manage_group.json"
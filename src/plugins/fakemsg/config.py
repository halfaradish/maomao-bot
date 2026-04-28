from typing import List

from nonebot.plugin import get_plugin_config
from pydantic import BaseModel


class Config(BaseModel):
    fakemsg_user_split: str = '|'
    fakemsg_max_daily_time: int = 5
    fakemsg_cmd: str = '伪消息'

config = get_plugin_config(Config)

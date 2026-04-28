from pydantic import BaseModel

class Config(BaseModel):
    bot_name: str = '谛听'
    nickname_changer_schedule_enable: bool = False
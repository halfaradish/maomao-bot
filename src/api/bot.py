from nonebot import get_bots, get_bot
from nonebot.adapters.onebot.v11 import Bot
from nonebot.exception import NoneBotException
from fastapi import APIRouter
from pydantic import BaseModel, ConfigDict
from typing import Optional, cast, Dict

router = APIRouter()

class BotStatusResponse(BaseModel):
    """Bot 状态响应模型"""
    status: str
    bot_count: int
    uptime: int
    bot_id: Optional[str] = None
    adapter: Optional[str] = None

    model_config = ConfigDict(
        json_schema_extra = {
            "example": {
                "status": "online",
                "bot_count": 1,
                "uptime": 3600
            }
        }
    )

@router.get(
    '/status',
    response_model=BotStatusResponse,
    summary="健康检查",
    description="无需认证，返回 Bot 基础状态"
)
async def health_check():
    bots: Dict[str, Bot] = cast(Dict[str, Bot], get_bots())

    if not bots:
        return BotStatusResponse(
            status="offline",
            bot_count=0,
            uptime=0,
            bot_id="",
            adapter=""
        )
    
    try:
        bot: Bot = cast(Bot, get_bot())
        bot_id = bot.self_id
        adapter_name: str = bot.adapter.get_name()
        status = "online" if bot else "offline"
    except NoneBotException:
        bot_id, bot = next(iter(bots.items()))
        adapter_name = bot.adapter.get_name()
        status = "online" if bot else "offline"

    return BotStatusResponse(
        status=status,
        bot_count=len(bots),
        uptime=3600,
        bot_id=bot_id,
        adapter=adapter_name
    )
import asyncio
import time

from fastapi import APIRouter, Depends, Request
from nonebot import get_bot, get_bots
from nonebot.adapters.onebot.v11 import Bot
from nonebot.exception import NoneBotException
from pydantic import BaseModel, ConfigDict
from sqlalchemy import text
from typing import Dict, Optional, cast

from src.api.deps import TokenPayload, verify_token
from src.common.database import async_session_factory
from src.common.icpc_database import icpc_async_session_factory
from src.common.oj_redis_pool import get_redis_connection
from src.config.response import success

router = APIRouter()

# 版本化管理 API（挂载于 /api/v1 下）
v1_router = APIRouter(prefix="/bot")

# 进程启动时间（模块导入即记录），用于计算真实运行时长
_PROCESS_START_TIME = time.time()


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
    uptime = int(time.time() - _PROCESS_START_TIME)

    if not bots:
        return BotStatusResponse(
            status="offline",
            bot_count=0,
            uptime=uptime,
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
        uptime=uptime,
        bot_id=bot_id,
        adapter=adapter_name
    )


# ---------------------------------------------------------------------------
# Bot 信息（WebUI 基础信息页）
# ---------------------------------------------------------------------------


async def _ping_mysql(session_factory) -> bool:
    """执行 SELECT 1 检测数据库连通性"""
    try:
        async with session_factory() as session:
            await session.execute(text("SELECT 1"))
        return True
    except Exception:
        return False


def _ping_redis_sync() -> bool:
    """同步执行 Redis ping（供 asyncio.to_thread 调用）"""
    try:
        with get_redis_connection(max_retries=0, retry_delay=0) as conn:
            return bool(conn.get_client().ping())
    except Exception:
        return False


@v1_router.get('/info', summary="Bot 详细信息")
async def bot_info(
    auth: TokenPayload = Depends(verify_token),
    request: Request = None,
):
    """返回 Bot 基础信息页所需的全部数据：
    QQ号/昵称/适配器/在线状态/所在群数量/真实运行时长/各连接状态。
    """
    bots: Dict[str, Bot] = cast(Dict[str, Bot], get_bots())

    bot_id: Optional[str] = None
    nickname: Optional[str] = None
    adapter: Optional[str] = None
    group_count: Optional[int] = None

    if bots:
        try:
            bot = cast(Bot, get_bot())
        except NoneBotException:
            bot = next(iter(bots.values()))
        bot_id = bot.self_id
        adapter = bot.adapter.get_name()

        # 昵称（陌生人信息接口）
        try:
            stranger = await bot.get_stranger_info(user_id=int(bot.self_id), no_cache=False)
            nickname = stranger.get("nickname") or None
        except Exception:
            nickname = None

        # 所在群数量（依赖 QQ 网关在线）
        try:
            group_count = len(await bot.get_group_list())
        except Exception:
            group_count = None

    # 三个连接状态并发检测
    bot_db_ok, icpc_db_ok, redis_ok = await asyncio.gather(
        _ping_mysql(async_session_factory),
        _ping_mysql(icpc_async_session_factory),
        asyncio.to_thread(_ping_redis_sync),
    )

    return success(
        data={
            "status": "online" if bots else "offline",
            "bot_count": len(bots),
            "bot_id": bot_id,
            "nickname": nickname,
            "adapter": adapter,
            "group_count": group_count,
            "uptime_seconds": int(time.time() - _PROCESS_START_TIME),
            "connections": {
                "bot_db": bot_db_ok,
                "icpc_db": icpc_db_ok,
                "redis": redis_ok,
            },
        },
        request=request,
    )

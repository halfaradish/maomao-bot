from nonebot import (
    get_app,
    logger,
    get_driver
)
from fastapi import (
    APIRouter,
    FastAPI,
    Request
)
from ..config.response import success
from .bot import router as bot_router
from .auth import router as auth_router
from .permissions import router as perm_router

api_router = APIRouter()
api_router.include_router(bot_router, tags=["bot信息"])
api_router.include_router(auth_router, prefix="/v1/auth")
api_router.include_router(perm_router)

app: FastAPI = get_app()
app.include_router(api_router, prefix="/api")

@app.get('/hello')
async def hello(request: Request):
    return success(
        request=request
    )

@get_driver().on_startup
async def consolo_setup_msg(): 
    logger.success(f"API routes have been registered. on http://127.0.0.1:{get_driver().config.port}")
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
from .captcha_ocr import router as captcha_ocr_router
from .bot import router as bot_router

api_router = APIRouter()
api_router.include_router(captcha_ocr_router, prefix="/ocr", tags=["ocr识别"])
api_router.include_router(bot_router, tags=["bot信息"])

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
from nonebot import get_app, logger
from fastapi import APIRouter, FastAPI

api_router = APIRouter()
9
from .captcha_ocr import router as captcha_ocr_router

api_router.include_router(captcha_ocr_router, prefix="/ocr", tags=["ocr识别"])

app: FastAPI = get_app()
app.include_router(api_router, prefix="/api")



logger.success("API routes have been registered.")
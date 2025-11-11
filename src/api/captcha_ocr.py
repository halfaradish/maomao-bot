from nonebot import logger
from fastapi import (
    APIRouter,
    Request,
    Query,    
    UploadFile,
    File,
    Form
)
from pydantic import BaseModel
import io
from functools import wraps
from time import time
from ..common.captcha_ocr import recognize_from_url, recognize
from ..config.local_config import NoneBotToken
from ..config import error, success

router = APIRouter()

class UrlItem(BaseModel):
    token: str | None = None
    url: str

@router.post('/url')
async def recognize_from_url_server(
    *,
    token: str = Query(''),
    item: UrlItem,
    req: Request
):
    try:
        # 检查是否传入token
        if not token and not item.token:
            return error(message="token未传入", request=req)
        
        token = token if token else item.token

        # 检查token是否正确
        if not token == NoneBotToken.DITING_API_ACCESS_TOKEN:
            return error(
                code=403,
                request=req
            )
        
        # ocr识别
        captcha: str = recognize_from_url(url=item.url)
        logger.debug(f"成功识别验证码：{captcha}")

        return success(
            data={
                "captcha": captcha
            },
            request=req
        )
    except Exception as e:
        logger.error(f"{req.url.path} 发生错误: {e}")
        return error(
            request=req
        )
    
@router.post('/bytes')
async def recognize_from_bytes_server(
    *, 
    query_token: str = Query(''),
    file: UploadFile = File(...),
    token: str | None = Form(...),
    req: Request
):
    """
    通过二进制数据识别验证码
    使用文件上传的方式传递二进制数据
    """
    try:
        # 检查是否传入token
        if not query_token and not token:
            return error(message="token未传入", request=req)
        token = token if token else query_token

        # 检查token是否正确
        if not token == NoneBotToken.DITING_API_ACCESS_TOKEN:
            return error(
                code=403,
                request=req
            )
        
        # 读取文件内容
        image_bytes = await file.read()
        
        # ocr识别
        captcha: str = recognize(image=image_bytes)
        logger.debug(f"成功识别验证码：{captcha}")

        return success(
            data={
                "captcha": captcha
            },
            request=req
        )
    except Exception as e:
        logger.error(f"{req.url.path} 发生错误: {e}")
        return error(
            message=str(e),
            request=req
        )
    
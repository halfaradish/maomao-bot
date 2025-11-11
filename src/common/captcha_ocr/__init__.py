"""
验证码识别OCR包

支持本地图片与网络图片的识别，提供API接口

"""
from .captcha_ocr import (

    CaptchaOCR,

    InvalidURLError,
    InvalidImageError,
    NetworkError,

    recognize,
    recognize_from_url

)

__version__ = "1.0.0"
__author__ = "nightmoonx"
__description__ = "验证码OCR识别Python包"

__all__ = [
    "CaptchaOCR",
    "InvalidImageError",
    "NetworkError",
    "InvalidURLError",
    "recognize",
    "recognize_from_url"
]
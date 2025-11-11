import io
import requests
import pathlib
import ddddocr
from typing import Union

class InvalidImageError(Exception):
    """当图片初始化失败时抛出异常"""
    pass
class NetworkError(Exception):
    """当网络请求失败时抛出异常"""
    pass

class InvalidURLError(Exception):
    """当URL无效时抛出异常"""
    pass

class CaptchaOCR:
    """
    验证码OCR识别类
    使用ddddocr作为引擎
    """
    def __init__(self):
        """初始化引擎"""
        try:
            self.ocr=ddddocr.DdddOcr(show_ad=False)
        except Exception as e:
            raise RuntimeError(f"初始化引擎失败：{str(e)}")
    def recognize(self, image:Union[str , pathlib.Path , bytes , io.BytesIO]):
        """
        核心功能：接受图片对象，进行OCR识别，返回字符串
        image: 支持以下四种类型的图片输入：
                - str: 图片在本地的文件路径
                - pathlib.Path: Python的路径对象
                - bytes: 图片的二进制数据
                - io.BytesIO: 内存中的字节流对象
        Returns:
            str:识别验证码内容，失败则返回字符串
        """
        try:
            if isinstance(image, str):
                try:
                    with open(image, 'rb') as f:
                        image_bytes = f.read()
                except FileExistsError:
                    raise InvalidImageError(f"文件不存在:{str(image)}")
                except Exception as e:
                    raise InvalidImageError(f"文件读取失败:{str(e)}")

            elif isinstance(image,pathlib.Path):
                if not image.exists():
                    raise InvalidImageError(f"图片不存在:{image}")
                try:
                    with open(image, "rb") as f :
                        image_bytes = f.read()
                except Exception as e:
                    raise InvalidImageError(f"读取图片文件失败:{str(e)}")

            elif isinstance(image,bytes):
                image_bytes = image

            elif isinstance(image,io.BytesIO):
                image_bytes = image.getvalue()

            else:
                raise InvalidImageError(f"不支持图片类型：{type(image).__name__}")

            if not image_bytes:
                raise InvalidImageError("图片数据为空")

            try:
                result = self.ocr.classification(image_bytes)
                return result if result else None
            except Exception as e:
                print(f"OCR识别过程中发生错误: {str(e)}")
                return None
        except InvalidImageError:
            raise
        except Exception as e:
            raise InvalidImageError(f"超出预期范围异常:{str(e)}")

    def recognize_from_url(self,url : str):
        """
        URL识别：接收图片URL，OCR识别图片，返回字符串
        """

        if not url or not isinstance(url,str):
            raise InvalidURLError("无效的URL")

        if not (url.startswith('http://') or url.startswith('https://')):
            raise InvalidURLError("URL必须以http://或https://开头")

        try:

            response= requests.get(url,timeout=10)
            response.raise_for_status()
            image_bytes =response.content

            return self.recognize(image_bytes)

        except requests.exceptions.MissingSchema:
            raise InvalidURLError("URL格式无效，缺少协议部分")
        except requests.exceptions.ConnectionError:
            raise NetworkError(f"无法连接到服务器: {url}")
        except requests.exceptions.Timeout:
            raise NetworkError(f"请求超时: {url}")
        except requests.exceptions.HTTPError as e:
            raise NetworkError(f"HTTP错误: {e.response.status_code} - {url}")
        except Exception as e:
            raise NetworkError(f"下载图片时发生错误: {str(e)}")


ocr_instance = CaptchaOCR()

# 提供便捷函数
def recognize(image: Union[str, pathlib.Path, bytes, io.BytesIO]):
    """便捷函数：直接调用核心识别功能"""
    return ocr_instance.recognize(image)

def recognize_from_url(url: str):
    """便捷函数：直接调用URL识别功能"""
    return ocr_instance.recognize_from_url(url)




























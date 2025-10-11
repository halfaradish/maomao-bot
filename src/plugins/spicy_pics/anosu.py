from nonebot import logger
import requests
import json
import os
from urllib.parse import urlparse
from nonebot.adapters.onebot.v11 import GroupMessageEvent, Bot

from ...config import DiTingData

SAVE_DIR = os.path.abspath(DiTingData.IMAGES_DIR)
if not os.path.exists(SAVE_DIR):
    os.makedirs(SAVE_DIR, exist_ok=True)
    logger.info(f"创建 spicy_pics 插件图片存放目录: {SAVE_DIR}")
API_URL = "https://image.anosu.top/pixiv/json"
ANOSU_HEADERS = {"Content-Type": "application/json"}
PIXIV_HEADERS = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'
}

class Anosu:
    """Anosu API interaction class"""

    def __init__(self):
        self.api_url = API_URL
        self.anosu_headers = ANOSU_HEADERS
        self.save_dir = SAVE_DIR
        self.pixiv_headers = PIXIV_HEADERS

    def _get_random_image_data(self, tags: list[str] = None, r18: int = 0):
        """获取随机涩图"""
        data = {
            "tags": tags if tags else [],
            "r18": r18
        }
        try:
            response = requests.post(
                self.api_url,
                headers=self.anosu_headers,
                data=json.dumps(data)
            )
            response.raise_for_status()
            result = response.json()
            return result
        except requests.exceptions.RequestException as e:
            logger.opt(exception=True).error(f"从 anosu 获取涩图失败: {e}")
            return None
        except json.JSONDecodeError as e:
            logger.opt(exception=True).error(f"解析 anosu 响应失败: {e}")
            return None
        
    async def _download_image(self, img_url: str, save_dir: str = SAVE_DIR) -> str:
        """下载图片到指定目录"""
        try:
            os.makedirs(save_dir, exist_ok=True)
            # 提取文件名
            parsed_url = urlparse(img_url)
            filename = os.path.basename(parsed_url.path)
            if not filename:
                filename = f"image_{hash(img_url)}.jpg"

            # 保存地址
            save_path = os.path.join(self.save_dir, filename)

            headers = self.pixiv_headers

            logger.info(f"开始下载图片 {img_url}")
            response = requests.get(img_url, stream=True, headers=headers)
            
            if response.status_code == 200:
                # 保存图片
                with open(save_path, 'wb') as f:
                    for chunk in response.iter_content(chunk_size=1024):
                        if chunk:
                            f.write(chunk)
                logger.info(f"图片下载成功: {save_path}")
                return save_path
            else:
                logger.error(f"图片下载失败，状态码: {response.status_code}")
                return None
        except Exception as e:
            logger.error(f"下载图片时出错: {e}")
            return None
        
    async def get_img(self, tags: list[str] = None, r18: int = 0, event: GroupMessageEvent = None, bot: Bot = None):
        """获取一张涩图"""
        img_data: list = self._get_random_image_data(tags=tags, r18=r18)
        if not img_data:
            return None
        img_url: str = img_data[0]['url']

        await bot.send(event=event, message="正在下载图片...")
        save_path: str = await self._download_image(img_url=img_url)
        if not save_path:
            logger.error("save_path 不存在")
            return None
        return save_path
    
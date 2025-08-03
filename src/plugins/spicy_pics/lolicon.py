from nonebot import logger
import requests
import json
import os
from urllib.parse import urlparse

SAVE_DIR = os.path.abspath("data/tmp/")
API_URL = "https://api.lolicon.app/setu/v2"
LOLICON_HEADERS = {"Content-Type": "application/json"}
PIXIV_HEADERS = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'
}

class Lolicon:
    """Lolicon API interaction class"""

    def __init__(self):
        self.api_url = API_URL
        self.lolicon_headers = LOLICON_HEADERS
        self.save_dir = SAVE_DIR
        self.pixiv_headers = PIXIV_HEADERS

    def _get_random_image_data(self, tags: list[str] = None, r18: int = 0):
        """获取随机涩图"""
        data = {
            tags: tags if tags else [],
            r18: r18,
        }
        try:
            response = requests.post(
                self.api_url,
                headers=self.lolicon_headers,
                data=json.dumps(data)
            )
            response.raise_for_status()
            result = response.json()
            return result
        except requests.exceptions.RequestException as e:
            logger.opt(exception=True).error(f"从 lolicon 获取涩图失败: {e}")
            return None
        except json.JSONDecodeError as e:
            logger.opt(exception=True).error(f"解析 lolicon 响应失败: {e}")
            return None
        
    def _download_image(self, img_url: str, save_dir: str = SAVE_DIR) -> str:
        """下载图片并保存到指定目录"""
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
                #保存图片
                with open(save_path, 'wb') as f:
                    for chunk in response.iter_content(chunk_size=1024):
                        if chunk:
                            f.write(chunk)
                logger.info(f"图片下载成功: {save_path}")
                return save_path
            else:
                logger.opt(exception=True).error(f"图片下载失败，状态码：{response.status_code}")
                return None
        except Exception as e:
            logger.opt(exception=True).error(f"下载图片时出错 {e}")
            return None
        
    def get_img(self, tags: list[str] = None, r18: int = 0):
        """获取一张涩图"""
        img_data: dict = self._get_random_image_data(tags=tags, r18=r18)
        if img_data == None:
            return None
        img_url: str = img_data["data"][0]["urls"]["original"]

        save_path: str = self._download_image(img_url=img_url)
        if save_path == None:
            return None
        return save_path
    
if __name__ == "__main__":
    lolicon = Lolicon()
    save_path = lolicon.get_img()
    if save_path:
        logger.info(f"图片已保存：{save_path}")
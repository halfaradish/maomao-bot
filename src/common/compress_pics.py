import glob
import os
from PIL import Image
import asyncio
import shutil
from nonebot import logger

DIR = os.path.abspath("./data/tmp")
COMPRESS_DIR = os.path.abspath("./data/pictures")
MAX_DIMENSION = 1280

class CompressPic(object):
    # 配置参数集中管理
    # MAX_DIMENSION = 1280
    DEFAULT_JPG_QUALITY = 85
    DEFAULT_PNG_COMPRESS_LEVEL = 6
    SUPPORTED_FORMATS = ('.jpg', '.jpeg', '.png', '.bmp', '.gif')

    def __init__(self, input_dir: str = "./data/tmp", output_dir: str = "./data/pictures"):
        self.DIR = os.path.abspath(input_dir)
        self.COMPRESS_DIR = os.path.abspath(output_dir)
        self.supported_formats = self.SUPPORTED_FORMATS

    def calculate_new_size(self, original_width, original_height):
        """计算保持比例的新尺寸，确保最长边不超过MAX_DIMENSION"""
        # 确定原始图片的长边
        if original_width > original_height:
            # 宽度是长边
            scale = MAX_DIMENSION / original_width
            new_width = MAX_DIMENSION
            new_height = int(original_height * scale)
        else:
            # 高度是长边
            scale = MAX_DIMENSION / original_height
            new_height = MAX_DIMENSION
            new_width = int(original_width * scale)
        return (new_width, new_height)
    
    async def compress_all_image(self):
        """按比例压缩目录中的所有图片"""
        os.makedirs(self.COMPRESS_DIR, exist_ok=True)
        for fmt in self.supported_formats:
            for filename in glob.glob(os.path.join(self.DIR, f"*{fmt}")):
                await self._process_single_image(filename)

    async def compress_one_image(self, img_path: str):
        """压缩单张图片"""
        os.makedirs(self.COMPRESS_DIR, exist_ok=True)
        compress_path = await self._process_single_image(img_path)
        return compress_path

    async def _process_single_image(self, img_path: str):
        """处理单张图片的压缩逻辑"""
        try:
            with Image.open(img_path) as img:
                original_width, original_height = img.size

                if original_width <= MAX_DIMENSION and original_height <= MAX_DIMENSION:
                    logger.info(f"图片 {img_path} 不需要压缩，直接复制")
                    shutil.copy(img_path, self.COMPRESS_DIR)
                    return

                new_size = self.calculate_new_size(original_width, original_height)
                logger.info(f"压缩图片 {img_path}: {original_width}*{original_height} -> {new_size[0]}*{new_size[1]}")

                resized_img = img.resize(new_size, Image.Resampling.LANCZOS)
                saved_path = self._get_saved_path(img_path)
                self._save_image(resized_img, saved_path, img_path)
                return saved_path
        except Exception as e:
            logger.error(f"处理图片 {img_path} 时出错: {e}")

    def _get_saved_path(self, img_path: str) -> str:
        """生成压缩后的图片保存路径"""
        file_basename = os.path.basename(img_path)
        name, ext = os.path.splitext(file_basename)
        return os.path.join(self.COMPRESS_DIR, f"{name}_compressed{ext}")

    def _save_image(self, img: Image.Image, saved_path: str, original_path: str):
        """根据图片格式保存压缩后的图片"""
        ext = os.path.splitext(original_path)[1].lower()
        if ext in ['.jpg', '.jpeg']:
            img.save(saved_path, quality=self.DEFAULT_JPG_QUALITY, optimize=True)
        elif ext == '.png':
            img.save(saved_path, optimize=True, compress_level=self.DEFAULT_PNG_COMPRESS_LEVEL)
        else:
            img.save(saved_path)
        logger.info(f"压缩后的图片已保存到 {saved_path}")

if __name__ == "__main__":
    compressor = CompressPic()
    asyncio.run(compressor.compress_all_image())
    logger.info("图片压缩完成！")
                        
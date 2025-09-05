from nonebot import logger
from nonebot.adapters.onebot.v11 import MessageSegment

from pathlib import Path

class BuildUri:
    @classmethod
    def create_napcat_file_uri(cls, file_path):
        # 获取绝对路径
        abs_path = Path(file_path).absolute().as_posix()

        pattern = "/napcat/app/data/"
        last_index = str(abs_path).rfind(pattern)

        if last_index != -1:
            result_path = str(abs_path)[last_index + len(pattern):]

        uri = f"file:///app/data/{result_path}"
        logger.info(f"the file uri in napcat-container is: {uri}")
        return uri
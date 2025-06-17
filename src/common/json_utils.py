import json
import os
import platform
from nonebot import logger
from typing import Any, Dict, List, Optional, Union, Tuple

class JsonUtils:
    """
    JSON 文件操作
    """
    windows_relative_url = r".\data"
    linux_relative_url = "./data"
    macos_relative_url = "./data"

    @staticmethod
    def __pre_built_file(file: str, default: Optional[Union[str, dict, Any]] = None) -> bool:
        if not os.path.exists(file):
            logger.info(f"当前文件: {file} 不存在, 正在尝试创建所需的 json 文件")
            dir_path = os.path.dirname(file)

            # 尝试创建文件
            if dir_path and not os.path.exists(dir_path):
                try:
                    os.makedirs(dir_path, exist_ok=True)
                    logger.info(f"{dir_path} 目录创建成功")
                except Exception as e:
                    logger.opt(exception=True).warning(f"{dir_path} 目录创建失败: {e}")
                    return False

            # 往目标文件写入默认内容
            with open(file, "w", encoding="utf-8") as f:
                if default is not None:
                    if isinstance(default, str):
                        f.write(default)
                    elif isinstance(default, dict):
                        try:
                            json_str = json.dumps(default, indent=4, ensure_ascii=False)
                            f.write(json_str)
                        except TypeError as e:
                            raise TypeError(f"字典无法序列化为JSON: {e}")
                    else:
                        f.write(str(default))
                else:
                    f.write("{}")
            return True # 文件时新建的
        logger.info(f"{file} 已存在")
        return False # 文件已存在
    
    @classmethod
    def __get_relative_url(cls, filename: str):
        """根据操作系统, 获取文件相对文件路径"""
        os_name = platform.system()
        logger.info(f"正在构建 {filename} 在当前系统 {os_name} 下的相对路径")
        if os_name == "Windows":
            relative_url = cls.windows_relative_url
        elif os_name == "Linux":
            relative_url = cls.linux_relative_url
        elif os_name == "Darwin":
            relative_url = cls.macos_relative_url
        file_url = os.path.join(relative_url, filename)
        return file_url

    
    @classmethod
    def read(cls, filename: str, *default: Any) -> Tuple[Union[dict, list, Any], bool]:
        """
        读取JSON文件

        :param filename: 文件名（相对路径）
        :param default: 可选，文件不存在时的默认内容
        :return: (文件内容, 是否为新创建的文件)
        """
        # 构建完整文件路径
        file_url = cls.__get_relative_url(filename)

        # 默认处理参数
        default_value = default[0] if default else None

        is_new = cls.__pre_built_file(file_url, default_value)

        try:
            with open(file_url, "r", encoding="utf-8") as f:
                content = json.load(f)
            return (content, is_new)
        except json.JSONDecodeError as e:
            logger.opt(exception=True).warning(f"{file_url} 文件JSON解析失败: {e}")
            return (default_value, is_new)
        except Exception as e:
            logger.opt(exception=True).warning(f"{file_url} 文件读取失败: {e}")
            return (default_value, is_new)
        
    @classmethod
    def write(cls, filename: str, content: Union[dict, list, Any]) -> bool:
        """
        写入JSON文件

        :param filename: 文件名（相对路径）
        :param content: 要写入的内容
        :return: 是否写入成功
        """
        file_url = cls.__get_relative_url(filename)

        # 确保文件存在
        # if not cls.__pre_built_file(file_url):
        #     logger.error(f"无法创建或访问文件 {file_url}")
        #     return False
        cls.__pre_built_file(file_url)

        try:
            with open(file_url, "w", encoding="utf-8") as f:
                json.dump(content, f, indent=4, ensure_ascii=False)
            return True
        except Exception as e:
            logger.opt(exception=True).warning(f"{file_url} 文件写入失败: {e}")
            return False
        

    @classmethod
    def update(cls, filename: str, updates: Dict[str, Any]) -> bool:
        """
        更新JSON文件中的内容

        :param filename: 文件名（相对路径）
        :param updates: 要更新的内容
        :return: 是否更新成功
        """
        content, _ = cls.read(filename)
        
        if not isinstance(content, dict):
            logger.error(f"{filename} 文件内容不是字典，无法更新")
            return False
        
        content.update(updates)
        
        return cls.write(filename, content)
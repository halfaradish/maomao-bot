import json
import os
import threading
from nonebot import logger
from typing import Any, Dict, Optional, Union, Tuple

from ..config import DiTingData

class JsonUtils:
    """
    JSON 文件操作
    """
    # 文件锁字典，用于存储每个文件的锁
    _file_locks: Dict[str, threading.RLock] = {}
    # 全局锁，用于保护文件锁字典的访问
    _global_lock = threading.RLock()

    @classmethod
    def _get_file_lock(cls, file_path: str) -> threading.RLock:
        """
        获取指定文件的锁，如果不存在则创建
        
        :param file_path: 文件路径
        :return: 文件对应的锁
        """
        with cls._global_lock:
            if file_path not in cls._file_locks:
                cls._file_locks[file_path] = threading.RLock()
            return cls._file_locks[file_path]

    @classmethod
    def __pre_built_file(cls, file: str, default: Optional[dict] = None) -> bool:
        # 获取文件锁
        with cls._get_file_lock(file):
            is_new: bool = False  # 文件已存在
            default = default or {}
            if not os.path.exists(file):
                
                is_new = True  # 文件是新建的
                logger.debug(f"当前文件: {file} 不存在, 正在尝试创建所需的 json 文件")
                dir_path = os.path.dirname(file)

                # 尝试创建文件
                if dir_path and not os.path.exists(dir_path):
                    try:
                        os.makedirs(dir_path, exist_ok=True)
                        logger.debug(f"{dir_path} 目录创建成功")
                    except Exception as e:
                        logger.opt(exception=True).error(f"{dir_path} 目录创建失败: {e}")
                        return False
            # 往目标文件写入默认内容
            if is_new:
                with open(file, "w", encoding="utf-8") as f:
                    try:
                        json.dump(default, f, indent=4, ensure_ascii=False)
                    except TypeError as e:
                        raise TypeError(f"字典无法序列化为JSON: {e}")
                logger.debug(f"{file} 成功写入默认内容")
            else:
                try:
                    # 先读原内容
                    with open(file, "r", encoding="utf-8") as f:
                        content = json.load(f)

                    change: bool = False
                    # 更新
                    for key, value in default.items():
                        if key not in content:
                            content[key] = value
                            change = True
                    
                    if change:
                        # 写入更新的内容
                        with open(file, "w", encoding="utf-8") as f:
                            json.dump(content, f, indent=4, ensure_ascii=False)
                        logger.debug(f"{file} 内容已更新")
                    else:
                        logger.debug(f"{file} 对应键已存在，无需更新")
                except json.JSONDecodeError as e:
                    raise ValueError(f"文件 {file} 不是有效的JSON: {e}")
                except Exception as e:
                    raise RuntimeError(f"处理文件 {file} 时出错: {e}")
            return is_new

    
    @classmethod
    def __get_relative_url(cls, filename: str):
        """获取文件绝对路径"""
        data_url = DiTingData.NONEBOT_DATA_DIR
        file_url = os.path.join(data_url, filename)
        return file_url

    
    @classmethod
    def read(cls, filename: str, default: Optional[dict] = None) -> Tuple[Union[dict, list, Any], bool]:
        """
        读取JSON文件

        :param filename: 文件名（相对路径）
        :param default: 可选，文件不存在时的默认内容
        :return: (文件内容, 是否为新创建的文件)
        """
        # 构建完整文件路径
        file_url = cls.__get_relative_url(filename)
        
        # 获取文件锁
        with cls._get_file_lock(file_url):
            is_new = cls.__pre_built_file(file_url, default or {})

            try:
                with open(file_url, "r", encoding="utf-8") as f:
                    content = json.load(f)
                return (content, is_new)
            except json.JSONDecodeError as e:
                logger.opt(exception=True).warning(f"{file_url} 文件JSON解析失败: {e}")
                return (default, is_new)
            except Exception as e:
                logger.opt(exception=True).warning(f"{file_url} 文件读取失败: {e}")
                return (default, is_new)
        
    @classmethod
    def write(cls, filename: str, content: Union[dict, list, Any]) -> bool:
        """
        写入JSON文件

        :param filename: 文件名（相对路径）
        :param content: 要写入的内容
        :return: 是否写入成功
        """
        file_url = cls.__get_relative_url(filename)
        
        # 获取文件锁
        with cls._get_file_lock(file_url):
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
        # 构建完整文件路径
        file_url = cls.__get_relative_url(filename)
        
        # 获取文件锁
        with cls._get_file_lock(file_url):
            content, _ = cls.read(filename)
            
            if not isinstance(content, dict):
                logger.error(f"{filename} 文件内容不是字典，无法更新")
                return False
            
            content.update(updates)
            
            return cls.write(filename, content)
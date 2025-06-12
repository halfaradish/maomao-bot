import json
import os
from typing import Any, Dict, List, Optional, Union, Tuple

class JsonUtils:
    """
    JSON 文件操作
    """
    relative_url = ".\src\data"

    @staticmethod
    def __pre_built_file(file: str,
                         default: Optional[Union[str, dict, Any]] = None) -> bool:
        if not os.path.exists(file):
            dir_path = os.path.dirname(file)

            if dir_path and not os.path.exists(dir_path):
                os.makedirs(dir_path, exist_ok=True)

            with open(file, "w", encoding="utf-8") as f:
                if default is not None:
                    if isinstance(default, str):
                        f.write(default, dict)
                    elif isinstance(default, dict):
                        try:
                            json_str = json.dumps(default, indent=4, ensure_ascii=False)
                            f.write(json_str)
                        except TypeError as e:
                            raise TypeError(f"字典无法序列化为JSON: {e}")
                    else:
                        f.write(str(default))
                else:
                    f.write("")
            return True # 文件时新建的
        return False # 文件已存在
    
    @classmethod
    def read(cls, filename: str, *default: Any) -> Tuple[Union[dict, list, Any], bool]:
        """
        读取JSON文件

        :param filename: 文件名（相对路径）
        :param default: 可选，文件不存在时的默认内容
        :return: (文件内容, 是否为新创建的文件)
        """
        # 构建完整文件路径
        file_url = os.path.join(cls.relative_url, filename)

        # 默认处理参数
        default_value = default[0] if default else None

        is_new = cls.__pre_built_file(file_url, default_value)

        with open(file_url, "r", encoding="utf-8") as f:
            try:
                content =json.load(f)
            except json.JSONDecodeError:
                return (default_value if default_value else {}, is_new)

        return (content, is_new)
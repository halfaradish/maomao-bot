from nonebot import logger
from nonebot.adapters.onebot.v11 import MessageSegment

from pathlib import Path

from ..config import DiTingData

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
    
class GenerateProblemUrl:
    """根据对应平台的题目id产生题目链接"""
    __luogu_base_url: str = "https://www.luogu.com.cn/problem/"
    __cf_base_url: str = "https://codeforces.com/problemset/problem/"

    @classmethod
    def generate_cf_url(cls, problem_id: str):
        """
        根据Codeforces题目ID生成对应的题目URL
        
        Args:
            problem_id: 题目ID, 例如 "1845A" 或 "1A"
        
        Returns:
            对应的题目URL, 例如 "https://codeforces.com/problemset/problem/1845/A"
        """
        for i, char in enumerate(problem_id):
            if char.isalpha():
                contest_id_part = problem_id[:i]
                problem_index_part = problem_id[i:]
                return f"{cls.__cf_base_url}{contest_id_part}/{problem_index_part}"
        return cls.__cf_base_url

    @classmethod
    def generate_luogu_url(cls, problem_id: str):
        """
        根据洛谷题目id生成对应题目URL

        Args:
            problem_id: 题目ID，例如 'P1001'
        
        Returns:
            对应的题目url，例如 "https://www.luogu.com.cn/problem/P1001"
        """
        if problem_id:
            return f"{cls.__luogu_base_url}{problem_id}"
        return cls.__luogu_base_url
    
    @classmethod
    def get_problem_url(cls, problem_id: str, platform: str) -> str:
        """根据平台产生url"""
        if platform in ['洛谷']:
            return cls.generate_luogu_url(problem_id=problem_id)
        elif platform in ['CF']:
            return cls.generate_cf_url(problem_id=problem_id)
        return None
    
class GetSQL:
    """获取sql语句"""
    @classmethod
    def __get_full_url(cls, relative_file_path: str) -> str:
        """获取文件绝对路径"""
        base_path = Path(DiTingData.SQL_DIR)
        relative_file_path = Path(relative_file_path)
        return base_path / relative_file_path

    @classmethod
    def read_sql_file(cls, relative_file_path: str) -> str:
        """
        读取.sql文件并返回字符串内容

        Args:
            SQL类型 + 文件名称 如：read/get_sub_records.sql
            其他SQL类型：create/delete/read/update
        
        Returns:
            文件里的SQL语句
        """
        file_path = cls.__get_full_url(relative_file_path)
        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                sql = f.read()
            return sql
        except FileNotFoundError:
            logger.error(f"找不到SQL文件: {file_path}")
            return None
        except Exception as e:
            logger.error(f"读取文件时错误: {e}")
            return None

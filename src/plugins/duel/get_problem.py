import random
from typing import List, Dict
from nonebot import logger, get_plugin_config

from .config import Config
from ...common import get_icpc_db_connection
from ...common.utils import (
    GetSQL,
    GenerateProblemUrl
)

config = get_plugin_config(Config)

def _get_all_problem_id():
    """获取题库所有的题目id"""
    try:
        query = GetSQL.read_sql_file(config.GET_CF_OFFICIAL_PROBLEMS)
        with get_icpc_db_connection() as db:
            records = db.execute(query=query).fetchall()
            return records
    except Exception as e:
        logger.error(f"获取cf题库的题目id时出错：{e}")
        return []
    
def _match_id_by_rating_tags(rating: int, tags: List[str]) -> List[Dict]:
    """根据rating和tags获取题目id"""
    # 检查参数有效性
    if rating is None and not tags:
        return []  # 返回空列表而不是错误字符串
    
    with get_icpc_db_connection() as db:
        query = GetSQL.read_sql_file(config.GET_CF_OFFICIAL_PROBLEMS)
        params = []
        
        if rating is not None:
            query += "AND rating = %s\n"
            params.append(rating)
            
        if tags:
            tag_patterns = ['%' + tag.lower() + '%' for tag in tags]
            tag_conditions = " AND ".join(["JSON_SEARCH(LOWER(tags), 'all', %s) IS NOT NULL"] * len(tags))
            query += f"AND {tag_conditions}\n"
            params.extend(tag_patterns)
            
        try:
            records = db.execute(query, params).fetchall()
            return records
        except Exception as e:
            # 记录错误日志
            logger.error(f"查询数据库时出错: {str(e)}")
            return []  # 发生错误时返回空列表

def get_one_problem_by_random():
    """
    随机获取Codeforces题库中的url
    """
    # 获取题库中所有题目id
    problems = _get_all_problem_id()
    if not problems:
        return "无法从题库中找到题目"
    # 随机选取一个id
    problem = random.choice(problems)
    # 将题目id转化为Codeforces url
    problem_url = GenerateProblemUrl.generate_cf_url(problem_id=problem['problem_id'])
    return problem_url


def get_problem_id_by_rating_tags(rating: int, tags: List[str]):
    """
    根据rating和tags随机获取Codeforces题库中的一题url
    """
    problems = _match_id_by_rating_tags(rating=rating, tags=tags)
    if not problems:
        return f"无法根据所给的rating和tags找到题目: {rating} {tags}"
    problem = random.choice(problems)
    # problem_url = _generate_cf_url(problem['problem_id'])
    problem_url = GenerateProblemUrl.generate_cf_url(problem_id=problem['problem_id'])
    return problem_url
from ...common import get_icpc_db_connection
import random
from typing import List

def _get_all_problem_id():
    """获取题库所有的题目id"""
    with get_icpc_db_connection() as db:
        query = """
            SELECT id
            FROM CF_contest_official
            """
        records = db.execute(query=query).fetchall()
        return records
    
def _match_id_by_rating_tags(rating: int, tags: List[str]):
    """根据rating和tags获取题目id"""
    with get_icpc_db_connection() as db:
        query = """
        SELECT id
        FROM CF_contest_official
        WHERE rating = %s
        """
        query_tags = "AND JSON_CONTAINS(tags, JSON_QUOTE(%s))\n"
        if tags is not None:
            for i in range(len(tags)):
                query += query_tags
            records = db.execute(query, (rating, *tags)).fetchall()
        else:
            records = db.execute(query, (rating,)).fetchall()
        return records


def _generate_cf_url(problem_id: str) -> str:
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
            return f"https://codeforces.com/problemset/problem/{contest_id_part}/{problem_index_part}"
    return "https://codeforces.com/problemset/problem/"

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
    problem_url = _generate_cf_url(problem['id'])
    return problem_url


def get_problem_id_by_rating_tags(rating: int, tags: List[str]):
    """
    根据rating和tags随机获取Codeforces题库中的一题url
    """
    problems = _match_id_by_rating_tags(rating=rating, tags=tags)
    if not problems:
        return "无法根据所给的rating和tags找到题目: {rating} {tags}"
    problem = random.choice(problems)
    problem_url = _generate_cf_url(problem['id'])
    return problem_url
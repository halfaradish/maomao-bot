from ...common import get_icpc_db_connection
import random

def _get_all_problem_id():
    """获取题库所有的题目id"""
    with get_icpc_db_connection() as db:
        query = """
            SELECT id
            FROM CF_contest_official
            """
        records = db.execute(query=query).fetchall()
        return records

def _generate_cf_url(problem_id: str) -> str:
    """
    根据Codeforces题目ID生成对应的题目URL
    
    Args:
        problem_id: 题目ID, 例如 "1845A" 或 "1A"
    
    Returns:
        对应的题目URL, 例如 "https://codeforces.com/problemset/problem/18/45A"
    """
    if len(problem_id) < 2:
        contest_id_part = problem_id.zfill(2)
        problem_index_part = ''
    else:
        contest_id_part = problem_id[:2]
        problem_index_part = problem_id[2:]

    return f"https://codeforces.com/problemset/problem/{contest_id_part}/{problem_index_part}"

def get_one_problem_by_random():
    """
    随机获取Codeforces题库中的url
    """
    # 获取题库中所有题目id
    problems = _get_all_problem_id()
    # 随机选取一个id
    problem = random.choice(problems)
    # 将题目id转化为Codeforces url
    problem_url = _generate_cf_url(problem['id'])
    return problem_url
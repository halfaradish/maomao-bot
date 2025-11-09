import random
from typing import List, Dict
from datetime import datetime, date
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


def get_daily_problem():
    """
    获取每日题目 - 同一天内所有人返回同一题，且不重复
    """
    from ...common.json_utils import JsonUtils

    # 读取存储的数据
    data, _ = JsonUtils.read(config.filename, {
        "map": {},
        "quick_map": {},
        "daily_problems": {
            "history": [],  # 历史使用过的题目ID
            "current_date": None,  # 当前日期
            "current_problem": None  # 当前题目
        }
    })

    daily_data = data.get("daily_problems", {
        "history": [],
        "current_date": None,
        "current_problem": None
    })

    today = date.today().isoformat()

    # 如果今天已经有题目了，直接返回
    if daily_data.get("current_date") == today and daily_data.get("current_problem"):
        problem_url = GenerateProblemUrl.generate_cf_url(problem_id=daily_data["current_problem"])
        return problem_url

    # 获取所有题目
    all_problems = _get_all_problem_id()
    if not all_problems:
        return "无法从题库中找到题目"

    # 获取未使用过的题目
    history = daily_data.get("history", [])
    available_problems = [p for p in all_problems if p['problem_id'] not in history]

    # 如果没有可用题目，重置历史记录
    if not available_problems:
        available_problems = all_problems
        history = []

    # 随机选择一个题目
    selected_problem = random.choice(available_problems)
    problem_id = selected_problem['problem_id']

    # 更新数据
    daily_data["current_date"] = today
    daily_data["current_problem"] = problem_id
    daily_data["history"] = history + [problem_id]

    data["daily_problems"] = daily_data
    JsonUtils.update(config.filename, data)

    problem_url = GenerateProblemUrl.generate_cf_url(problem_id=problem_id)
    return problem_url


def get_problem_id_by_rating_tags(rating: int, tags: List[str]):
    """
    根据rating和tags随机获取Codeforces题库中的一题url
    """
    problems = _match_id_by_rating_tags(rating=rating, tags=tags)
    if not problems:
        return f"无法根据所给的rating和tags找到题目: {rating} {tags}"
    problem = random.choice(problems)
    problem_url = GenerateProblemUrl.generate_cf_url(problem_id=problem['problem_id'])
    return problem_url
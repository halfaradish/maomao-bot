# src/plugins/icpc_ac_monitor/mappings.py
"""城市拼音与学校名称映射加载及匹配/显示辅助"""

import json
import re
from typing import Dict, List

from nonebot import logger

from .state import CITY_MAP_FILE, SCHOOL_MAP_FILE


def _load_city_mapping() -> tuple[Dict[str, str], Dict[str, str]]:
    """加载 data/city_pinyin_map.json，返回中文->拼音、拼音->中文双向映射"""
    if not CITY_MAP_FILE.exists():
        logger.warning(f"未在 {CITY_MAP_FILE} 找到城市映射，赛站将保持原始拼音显示。")
        return {}, {}
    try:
        with CITY_MAP_FILE.open("r", encoding="utf-8") as f:
            data = json.load(f)
        if not isinstance(data, dict):
            raise ValueError("city_pinyin_map.json 内容不是字典。")
        forward = {}
        for zh, py in data.items():
            zh_name = str(zh).strip()
            py_slug = str(py).strip().lower()
            if not zh_name or not py_slug:
                continue
            forward[zh_name] = py_slug
        reverse = {py_slug: zh_name for zh_name, py_slug in forward.items()}
        return forward, reverse
    except Exception as e:
        logger.warning(f"加载城市映射失败：{e}")
        return {}, {}


CITY_TO_PINYIN, PINYIN_TO_CITY = _load_city_mapping()


def _load_school_mapping() -> Dict[str, List[str]]:
    """加载 data/school_name_map.json，返回中文名称->英文名称列表的映射"""
    if not SCHOOL_MAP_FILE.exists():
        logger.info(f"未在 {SCHOOL_MAP_FILE} 找到学校名称映射，将使用精确匹配。")
        return {}
    try:
        with SCHOOL_MAP_FILE.open("r", encoding="utf-8") as f:
            data = json.load(f)
        if not isinstance(data, dict):
            raise ValueError("school_name_map.json 内容不是字典。")
        result = {}
        for zh_name, aliases in data.items():
            zh_name = str(zh_name).strip()
            if not zh_name:
                continue
            # 支持字符串或列表格式
            if isinstance(aliases, str):
                alias_list = [aliases.strip()]
            elif isinstance(aliases, list):
                alias_list = [str(a).strip() for a in aliases if a]
            else:
                continue
            if alias_list:
                result[zh_name] = alias_list
        return result
    except Exception as e:
        logger.warning(f"加载学校名称映射失败：{e}")
        return {}


SCHOOL_NAME_MAP = _load_school_mapping()


def _is_school_match(organization: str, schools: List[str], school_map: Dict[str, List[str]]) -> bool:
    """
    检查 organization 是否匹配 schools 列表中的任一学校名称
    支持精确匹配和映射匹配（中英文名称映射）
    """
    if not organization:
        return False
    org = organization.strip()

    # 1. 精确匹配：直接检查 organization 是否在配置的学校列表中
    if org in schools:
        return True

    # 2. 映射匹配：检查 organization 是否匹配配置学校名称的英文别名
    for school in schools:
        aliases = school_map.get(school, [])
        if org in aliases:
            return True

    return False


def _resolve_city_display_name(raw: str) -> str:
    """将 URL 中的赛站拼音转换为中文名称"""
    if not raw:
        return raw
    slug = raw.lower()
    if slug in PINYIN_TO_CITY:
        return PINYIN_TO_CITY[slug]
    # 分割出可能的拼音片段（去掉数字、破折号等）
    tokens = [tok for tok in re.split(r"[^a-z]+", slug) if tok]
    for token in tokens:
        if token in PINYIN_TO_CITY:
            return PINYIN_TO_CITY[token]
    return raw


def _ensure_comp_display(meta: Dict) -> str:
    """保证 meta 中存在中文赛站名，并返回它"""
    if not isinstance(meta, dict):
        return ""
    display = meta.get("comp_display_name")
    if display:
        return display
    raw = meta.get("comp_name", "")
    display = _resolve_city_display_name(raw)
    meta["comp_display_name"] = display
    return display

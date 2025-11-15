from nonebot import (
    logger,
    get_plugin_config
)
from pydantic import BaseModel, field_validator
from typing import Optional, List, Dict, Any
from datetime import datetime, timedelta
import requests
from zoneinfo import ZoneInfo

from .config import Config

config = get_plugin_config(Config)

class ContestInfo(BaseModel):
    duration: int
    end: datetime
    event: str
    host: str
    href: str
    id: int
    n_problems: Optional[int] = None
    n_statistics: Optional[int] = None
    parsed_at: Optional[datetime] = None
    problems: Optional[list] = None
    resource: Optional[str]
    resource_id: int
    start: datetime

    @field_validator('start', 'end', 'parsed_at', mode='before')
    def parse_datetime(cls, v: Any) -> Any:
        if isinstance(v, str):
            # 解析为朴素时间（无tzinfo）
            naive_dt = datetime.fromisoformat(v)
            
            # 关键：明确指定这是UTC时间，不是本地时间！
            utc_zone = ZoneInfo("UTC")
            utc_dt = naive_dt.replace(tzinfo=utc_zone)
            
            return utc_dt
        return v

    def to_string(self) -> str:
        duration_minutes = self.duration / 60
        # 将datetime对象转化为字符串
        start_str = self.start.strftime('%Y-%m-%d %H:%M:%S')
        end_str = self.end.strftime('%Y-%m-%d %H:%M:%S')
        return (
            f"赛事: {self.event}\n"
            f"平台: {self.resource}\n"
            f"url: {self.href}\n"
            f"开始时间: {start_str}\n"
            f"结束时间: {end_str}\n"
            f"持续时间: {duration_minutes:.2f} 小时 | 题目数: {self.n_problems or '未知'}"
        )

class ContestFetcher:
    def __init__(self):
        self.username = config.clist_username
        self.api_key = config.clist_api_key
        self.base_url = config.clist_contest_fetch_base_url
        self.hours_ahead = config.clist_hours_ahead
        self.utc_zone = ZoneInfo("UTC")
        self.local_zone = ZoneInfo("Asia/Shanghai")
        # 平台映射
        self.platforms = {
            'codeforces': 1,
            'codechef': 2,
            'atcoder': 93,
            'leetcode': 102,
            'topcoder': 12,
            'hackerearth': 73,
            'hackerrank': 63,
            'google': 35,
            'csacademy': 90,
            'usaco': 25,
            'spoj': 26,
            'kaggle': 74,
            'yandex': 67,
        }

    def fetch_contests(self, platform_names: Optional[List[str]] = None, params: Optional[Dict] = None, hours_ahead: Optional[int] = None):

        if platform_names is None:
            platform_names = []
        if params is None:
            params = {}
        if hours_ahead is None:
            hours_ahead = self.hours_ahead

        # 获取当前东八区时间
        now_local = datetime.now(self.local_zone).replace(hour=0, minute=0, second=0, microsecond=0)

        # 转化为utc时间
        now_utc = now_local.astimezone(self.utc_zone)
        future_utc = now_utc + timedelta(hours=self.hours_ahead)

        # 定义默认参数
        default_params = {
            'username': self.username,
            'api_key': self.api_key,
            'start__gte': now_utc.isoformat(),  # 添加Z表示UTC时间
            'start__lt': future_utc.isoformat(),
            'order_by': 'start'
        }

        # 添加平台筛选
        if platform_names:
            resource_ids = [self.platforms.get(name) for name in platform_names if name in self.platforms]
            if resource_ids:
                default_params['resource_id__in'] = ','.join(map(str, resource_ids))

        # 用用户传入的 params 覆盖默认参数
        default_params.update(params)

        try:
            logger.debug(f"请求参数: {default_params}")
            response = requests.get(url=self.base_url, params=default_params)
            response.raise_for_status()

            data: Dict = response.json()
            objects: List = data.get('objects', [])

            # 将josn信息转化为ContestInfo
            contests_info: List[ContestInfo] = [ContestInfo(**obj) for obj in objects]

            # 将utc时间转换为东八区
            contests_info = self.transform_to_local_time(contests_info=contests_info)

            logger.info(f"成功获取 {len(contests_info)} 场比赛信息")
            return contests_info
        
        except requests.exceptions.Timeout:
            logger.error("请求超时")
            return []
        except requests.exceptions.RequestException as e:
            logger.error(f"网络错误: {e}")
            return []
        except Exception as e:
            logger.error(f"获取比赛信息时发生错误: {e}")
            return []

    def transform_to_local_time(self, contests_info: List[ContestInfo]):
        """
        将ContestInfo列表中的UTC时间转换为本地时间（东八区）
        
        :param contest_info: ContestInfo对象列表，包含UTC时间
        :return: 转换后的ContestInfo对象列表，时间已转换为东八区
        """
        for contest in contests_info:
            # 转换 start 时间（从UTC到东八区）
            if contest.start:
                contest.start = contest.start.astimezone(self.local_zone)
            # 转换 end 时间
            if contest.end:
                contest.end = contest.end.astimezone(self.local_zone)
            # 转换 parsed_at 时间
            if contest.parsed_at:
                contest.parsed_at = contest.parsed_at.astimezone(self.local_zone)

        return contests_info


contest_fetcher = ContestFetcher()
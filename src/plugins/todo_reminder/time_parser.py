"""
Todo提醒插件时间解析器
支持多种时间格式的解析
"""

import re
from datetime import datetime, timedelta
from typing import Optional, Dict, Any
import pytz
from nonebot import logger


class TimeParser:
    """时间解析器类"""
    
    def __init__(self, timezone: str = "Asia/Shanghai"):
        self.timezone = pytz.timezone(timezone)
        
        # 时间模式配置
        self.patterns = {
            # 相对时间模式
            "relative": [
                (r"(\d+)分钟后", self._parse_minutes_later),
                (r"(\d+)小时后", self._parse_hours_later),
                (r"(\d+)天后", self._parse_days_later),
                (r"(\d+)周后", self._parse_weeks_later),
                (r"(\d+)个月后", self._parse_months_later),
            ],
            # 绝对时间模式
            "absolute": [
                (r"明天(\d+)点", self._parse_tomorrow_hour),
                (r"明天(\d+)点(\d+)分", self._parse_tomorrow_hour_minute),
                (r"明天(上午|下午|晚上)(\d+)点", self._parse_tomorrow_period_hour),
                (r"明天(上午|下午|晚上)(\d+)点(\d+)分", self._parse_tomorrow_period_hour_minute),
                (r"后天(\d+)点", self._parse_day_after_tomorrow_hour),
                (r"后天(\d+)点(\d+)分", self._parse_day_after_tomorrow_hour_minute),
                (r"后天(上午|下午|晚上)(\d+)点", self._parse_day_after_tomorrow_period_hour),
                (r"后天(上午|下午|晚上)(\d+)点(\d+)分", self._parse_day_after_tomorrow_period_hour_minute),
                (r"大后天(\d+)点", self._parse_day_after_day_after_tomorrow_hour),
                (r"大后天(\d+)点(\d+)分", self._parse_day_after_day_after_tomorrow_hour_minute),
                (r"大后天(上午|下午|晚上)(\d+)点", self._parse_day_after_day_after_tomorrow_period_hour),
                (r"大后天(上午|下午|晚上)(\d+)点(\d+)分", self._parse_day_after_day_after_tomorrow_period_hour_minute),
            ],
            # 重复时间模式
            "recurring": [
                (r"每天(\d+)点", self._parse_daily_hour),
                (r"每天(\d+)点(\d+)分", self._parse_daily_hour_minute),
                (r"每天(上午|下午|晚上)(\d+)点", self._parse_daily_period_hour),
                (r"每天(上午|下午|晚上)(\d+)点(\d+)分", self._parse_daily_period_hour_minute),
                (r"工作日(\d+)点", self._parse_workday_hour),
                (r"工作日(\d+)点(\d+)分", self._parse_workday_hour_minute),
                (r"工作日(上午|下午|晚上)(\d+)点", self._parse_workday_period_hour),
                (r"工作日(上午|下午|晚上)(\d+)点(\d+)分", self._parse_workday_period_hour_minute),
                (r"每周([一二三四五六日天])(\d+)点", self._parse_weekly_hour),
                (r"每周([一二三四五六日天])(\d+)点(\d+)分", self._parse_weekly_hour_minute),
                (r"每周([一二三四五六日天])(上午|下午|晚上)(\d+)点", self._parse_weekly_period_hour),
                (r"每周([一二三四五六日天])(上午|下午|晚上)(\d+)点(\d+)分", self._parse_weekly_period_hour_minute),
            ],
            # 具体日期时间模式
            "specific": [
                (r"(\d{4})-(\d{1,2})-(\d{1,2})\s+(\d{1,2}):(\d{1,2})", self._parse_specific_datetime),
                (r"(\d{1,2})-(\d{1,2})\s+(\d{1,2}):(\d{1,2})", self._parse_month_day_time),
                (r"(\d{1,2})月(\d{1,2})日\s+(\d{1,2}):(\d{1,2})", self._parse_chinese_date_time),
            ]
        }
        
        # 星期映射
        self.weekday_map = {
            "一": 0, "二": 1, "三": 2, "四": 3, "五": 4, "六": 5, "日": 6, "天": 6
        }
    
    def _get_current_time(self) -> datetime:
        """获取当前时间"""
        return datetime.now(self.timezone)
    
    def parse_time(self, time_str: str) -> Optional[Dict[str, Any]]:
        """
        解析时间字符串
        
        Args:
            time_str: 时间字符串
            
        Returns:
            解析结果字典，包含remind_time, remind_type, repeat_type等信息
        """
        if not time_str or not time_str.strip():
            return None
        
        time_str = time_str.strip()
        
        # 尝试各种模式
        for pattern_type, patterns in self.patterns.items():
            for pattern, parser_func in patterns:
                match = re.search(pattern, time_str)
                if match:
                    try:
                        result = parser_func(match)
                        if result:
                            result["original_string"] = time_str
                            result["pattern_type"] = pattern_type
                            return result
                    except Exception as e:
                        logger.warning(f"时间解析失败: {time_str}, 错误: {e}")
                        continue
        
        # 如果所有模式都失败，尝试直接解析
        return self._parse_direct_time(time_str)
    
    def _parse_minutes_later(self, match) -> Optional[Dict[str, Any]]:
        """解析X分钟后"""
        minutes = int(match.group(1))
        now = self._get_current_time()
        remind_time = now + timedelta(minutes=minutes)
        return {
            "remind_time": remind_time,
            "remind_type": "once",
            "repeat_type": None
        }
    
    def _parse_hours_later(self, match) -> Optional[Dict[str, Any]]:
        """解析X小时后"""
        hours = int(match.group(1))
        now = self._get_current_time()
        remind_time = now + timedelta(hours=hours)
        return {
            "remind_time": remind_time,
            "remind_type": "once",
            "repeat_type": None
        }
    
    def _parse_days_later(self, match) -> Optional[Dict[str, Any]]:
        """解析X天后"""
        days = int(match.group(1))
        now = self._get_current_time()
        remind_time = now + timedelta(days=days)
        return {
            "remind_time": remind_time,
            "remind_type": "once",
            "repeat_type": None
        }
    
    def _parse_weeks_later(self, match) -> Optional[Dict[str, Any]]:
        """解析X周后"""
        weeks = int(match.group(1))
        now = self._get_current_time()
        remind_time = now + timedelta(weeks=weeks)
        return {
            "remind_time": remind_time,
            "remind_type": "once",
            "repeat_type": None
        }
    
    def _parse_months_later(self, match) -> Optional[Dict[str, Any]]:
        """解析X个月后"""
        months = int(match.group(1))
        # 简单的月份计算，不考虑月份天数差异
        now = self._get_current_time()
        remind_time = now + timedelta(days=months * 30)
        return {
            "remind_time": remind_time,
            "remind_type": "once",
            "repeat_type": None
        }
    
    def _parse_tomorrow_period_hour(self, match) -> Optional[Dict[str, Any]]:
        """解析明天上午/下午/晚上X点"""
        period = match.group(1)
        hour = int(match.group(2))
        
        # 处理上午/下午/晚上的时间转换
        if period == "下午" and hour < 12:
            hour += 12
        elif period == "晚上" and hour < 12:
            hour += 12
        
        tomorrow = self._get_current_time() + timedelta(days=1)
        remind_time = tomorrow.replace(hour=hour, minute=0, second=0, microsecond=0)
        return {
            "remind_time": remind_time,
            "remind_type": "once",
            "repeat_type": None
        }
    
    def _parse_tomorrow_period_hour_minute(self, match) -> Optional[Dict[str, Any]]:
        """解析明天上午/下午/晚上X点Y分"""
        period = match.group(1)
        hour = int(match.group(2))
        minute = int(match.group(3))
        
        # 处理上午/下午/晚上的时间转换
        if period == "下午" and hour < 12:
            hour += 12
        elif period == "晚上" and hour < 12:
            hour += 12
        
        tomorrow = self._get_current_time() + timedelta(days=1)
        remind_time = tomorrow.replace(hour=hour, minute=minute, second=0, microsecond=0)
        return {
            "remind_time": remind_time,
            "remind_type": "once",
            "repeat_type": None
        }
    
    def _parse_day_after_tomorrow_period_hour(self, match) -> Optional[Dict[str, Any]]:
        """解析后天上午/下午/晚上X点"""
        period = match.group(1)
        hour = int(match.group(2))
        
        # 处理上午/下午/晚上的时间转换
        if period == "下午" and hour < 12:
            hour += 12
        elif period == "晚上" and hour < 12:
            hour += 12
        
        day_after_tomorrow = self._get_current_time() + timedelta(days=2)
        remind_time = day_after_tomorrow.replace(hour=hour, minute=0, second=0, microsecond=0)
        return {
            "remind_time": remind_time,
            "remind_type": "once",
            "repeat_type": None
        }
    
    def _parse_day_after_tomorrow_period_hour_minute(self, match) -> Optional[Dict[str, Any]]:
        """解析后天上午/下午/晚上X点Y分"""
        period = match.group(1)
        hour = int(match.group(2))
        minute = int(match.group(3))
        
        # 处理上午/下午/晚上的时间转换
        if period == "下午" and hour < 12:
            hour += 12
        elif period == "晚上" and hour < 12:
            hour += 12
        
        day_after_tomorrow = self._get_current_time() + timedelta(days=2)
        remind_time = day_after_tomorrow.replace(hour=hour, minute=minute, second=0, microsecond=0)
        return {
            "remind_time": remind_time,
            "remind_type": "once",
            "repeat_type": None
        }
    
    def _parse_day_after_day_after_tomorrow_period_hour(self, match) -> Optional[Dict[str, Any]]:
        """解析大后天上午/下午/晚上X点"""
        period = match.group(1)
        hour = int(match.group(2))
        
        # 处理上午/下午/晚上的时间转换
        if period == "下午" and hour < 12:
            hour += 12
        elif period == "晚上" and hour < 12:
            hour += 12
        
        day_after_day_after_tomorrow = self._get_current_time() + timedelta(days=3)
        remind_time = day_after_day_after_tomorrow.replace(hour=hour, minute=0, second=0, microsecond=0)
        return {
            "remind_time": remind_time,
            "remind_type": "once",
            "repeat_type": None
        }
    
    def _parse_day_after_day_after_tomorrow_period_hour_minute(self, match) -> Optional[Dict[str, Any]]:
        """解析大后天上午/下午/晚上X点Y分"""
        period = match.group(1)
        hour = int(match.group(2))
        minute = int(match.group(3))
        
        # 处理上午/下午/晚上的时间转换
        if period == "下午" and hour < 12:
            hour += 12
        elif period == "晚上" and hour < 12:
            hour += 12
        
        day_after_day_after_tomorrow = self._get_current_time() + timedelta(days=3)
        remind_time = day_after_day_after_tomorrow.replace(hour=hour, minute=minute, second=0, microsecond=0)
        return {
            "remind_time": remind_time,
            "remind_type": "once",
            "repeat_type": None
        }
    
    def _parse_tomorrow_hour(self, match) -> Optional[Dict[str, Any]]:
        """解析明天X点"""
        hour = int(match.group(1))
        tomorrow = self._get_current_time() + timedelta(days=1)
        remind_time = tomorrow.replace(hour=hour, minute=0, second=0, microsecond=0)
        return {
            "remind_time": remind_time,
            "remind_type": "once",
            "repeat_type": None
        }
    
    def _parse_tomorrow_hour_minute(self, match) -> Optional[Dict[str, Any]]:
        """解析明天X点Y分"""
        hour = int(match.group(1))
        minute = int(match.group(2))
        tomorrow = self._get_current_time() + timedelta(days=1)
        remind_time = tomorrow.replace(hour=hour, minute=minute, second=0, microsecond=0)
        return {
            "remind_time": remind_time,
            "remind_type": "once",
            "repeat_type": None
        }
    
    def _parse_day_after_tomorrow_hour(self, match) -> Optional[Dict[str, Any]]:
        """解析后天X点"""
        hour = int(match.group(1))
        day_after_tomorrow = self._get_current_time() + timedelta(days=2)
        remind_time = day_after_tomorrow.replace(hour=hour, minute=0, second=0, microsecond=0)
        return {
            "remind_time": remind_time,
            "remind_type": "once",
            "repeat_type": None
        }
    
    def _parse_day_after_tomorrow_hour_minute(self, match) -> Optional[Dict[str, Any]]:
        """解析后天X点Y分"""
        hour = int(match.group(1))
        minute = int(match.group(2))
        day_after_tomorrow = self._get_current_time() + timedelta(days=2)
        remind_time = day_after_tomorrow.replace(hour=hour, minute=minute, second=0, microsecond=0)
        return {
            "remind_time": remind_time,
            "remind_type": "once",
            "repeat_type": None
        }
    
    def _parse_day_after_day_after_tomorrow_hour(self, match) -> Optional[Dict[str, Any]]:
        """解析大后天X点"""
        hour = int(match.group(1))
        day_after_day_after_tomorrow = self._get_current_time() + timedelta(days=3)
        remind_time = day_after_day_after_tomorrow.replace(hour=hour, minute=0, second=0, microsecond=0)
        return {
            "remind_time": remind_time,
            "remind_type": "once",
            "repeat_type": None
        }
    
    def _parse_day_after_day_after_tomorrow_hour_minute(self, match) -> Optional[Dict[str, Any]]:
        """解析大后天X点Y分"""
        hour = int(match.group(1))
        minute = int(match.group(2))
        day_after_day_after_tomorrow = self._get_current_time() + timedelta(days=3)
        remind_time = day_after_day_after_tomorrow.replace(hour=hour, minute=minute, second=0, microsecond=0)
        return {
            "remind_time": remind_time,
            "remind_type": "once",
            "repeat_type": None
        }
    
    def _parse_daily_period_hour(self, match) -> Optional[Dict[str, Any]]:
        """解析每天上午/下午/晚上X点"""
        period = match.group(1)
        hour = int(match.group(2))
        
        # 处理上午/下午/晚上的时间转换
        if period == "下午" and hour < 12:
            hour += 12
        elif period == "晚上" and hour < 12:
            hour += 12
        
        # 计算下一个该时间点
        now = self._get_current_time()
        remind_time = now.replace(hour=hour, minute=0, second=0, microsecond=0)
        if remind_time <= now:
            remind_time += timedelta(days=1)
        return {
            "remind_time": remind_time,
            "remind_type": "daily",
            "repeat_type": "daily"
        }
    
    def _parse_daily_period_hour_minute(self, match) -> Optional[Dict[str, Any]]:
        """解析每天上午/下午/晚上X点Y分"""
        period = match.group(1)
        hour = int(match.group(2))
        minute = int(match.group(3))
        
        # 处理上午/下午/晚上的时间转换
        if period == "下午" and hour < 12:
            hour += 12
        elif period == "晚上" and hour < 12:
            hour += 12
        
        now = self._get_current_time()
        remind_time = now.replace(hour=hour, minute=minute, second=0, microsecond=0)
        if remind_time <= now:
            remind_time += timedelta(days=1)
        return {
            "remind_time": remind_time,
            "remind_type": "daily",
            "repeat_type": "daily"
        }
    
    def _parse_workday_period_hour(self, match) -> Optional[Dict[str, Any]]:
        """解析工作日上午/下午/晚上X点"""
        period = match.group(1)
        hour = int(match.group(2))
        
        # 处理上午/下午/晚上的时间转换
        if period == "下午" and hour < 12:
            hour += 12
        elif period == "晚上" and hour < 12:
            hour += 12
        
        remind_time = self._get_next_workday_time(hour, 0)
        return {
            "remind_time": remind_time,
            "remind_type": "workday",
            "repeat_type": "workday"
        }
    
    def _parse_workday_period_hour_minute(self, match) -> Optional[Dict[str, Any]]:
        """解析工作日上午/下午/晚上X点Y分"""
        period = match.group(1)
        hour = int(match.group(2))
        minute = int(match.group(3))
        
        # 处理上午/下午/晚上的时间转换
        if period == "下午" and hour < 12:
            hour += 12
        elif period == "晚上" and hour < 12:
            hour += 12
        
        remind_time = self._get_next_workday_time(hour, minute)
        return {
            "remind_time": remind_time,
            "remind_type": "workday",
            "repeat_type": "workday"
        }
    
    def _parse_weekly_period_hour(self, match) -> Optional[Dict[str, Any]]:
        """解析每周X上午/下午/晚上Y点"""
        weekday = self.weekday_map.get(match.group(1))
        period = match.group(2)
        hour = int(match.group(3))
        
        if weekday is None:
            return None
        
        # 处理上午/下午/晚上的时间转换
        if period == "下午" and hour < 12:
            hour += 12
        elif period == "晚上" and hour < 12:
            hour += 12
        
        remind_time = self._get_next_weekday_time(weekday, hour, 0)
        return {
            "remind_time": remind_time,
            "remind_type": "weekly",
            "repeat_type": "weekly"
        }
    
    def _parse_weekly_period_hour_minute(self, match) -> Optional[Dict[str, Any]]:
        """解析每周X上午/下午/晚上Y点Z分"""
        weekday = self.weekday_map.get(match.group(1))
        period = match.group(2)
        hour = int(match.group(3))
        minute = int(match.group(4))
        
        if weekday is None:
            return None
        
        # 处理上午/下午/晚上的时间转换
        if period == "下午" and hour < 12:
            hour += 12
        elif period == "晚上" and hour < 12:
            hour += 12
        
        remind_time = self._get_next_weekday_time(weekday, hour, minute)
        return {
            "remind_time": remind_time,
            "remind_type": "weekly",
            "repeat_type": "weekly"
        }
    
    def _parse_daily_hour(self, match) -> Optional[Dict[str, Any]]:
        """解析每天X点"""
        hour = int(match.group(1))
        # 计算下一个该时间点
        now = self._get_current_time()
        remind_time = now.replace(hour=hour, minute=0, second=0, microsecond=0)
        if remind_time <= now:
            remind_time += timedelta(days=1)
        return {
            "remind_time": remind_time,
            "remind_type": "daily",
            "repeat_type": "daily"
        }
    
    def _parse_daily_hour_minute(self, match) -> Optional[Dict[str, Any]]:
        """解析每天X点Y分"""
        hour = int(match.group(1))
        minute = int(match.group(2))
        now = self._get_current_time()
        remind_time = now.replace(hour=hour, minute=minute, second=0, microsecond=0)
        if remind_time <= now:
            remind_time += timedelta(days=1)
        return {
            "remind_time": remind_time,
            "remind_type": "recurring",
            "repeat_type": "daily"
        }
    
    def _parse_workday_hour(self, match) -> Optional[Dict[str, Any]]:
        """解析工作日X点"""
        hour = int(match.group(1))
        remind_time = self._get_next_workday_time(hour, 0)
        return {
            "remind_time": remind_time,
            "remind_type": "recurring",
            "repeat_type": "workday"
        }
    
    def _parse_workday_hour_minute(self, match) -> Optional[Dict[str, Any]]:
        """解析工作日X点Y分"""
        hour = int(match.group(1))
        minute = int(match.group(2))
        remind_time = self._get_next_workday_time(hour, minute)
        return {
            "remind_time": remind_time,
            "remind_type": "recurring",
            "repeat_type": "workday"
        }
    
    def _parse_weekly_hour(self, match) -> Optional[Dict[str, Any]]:
        """解析每周X点"""
        weekday = self.weekday_map.get(match.group(1))
        hour = int(match.group(2))
        if weekday is None:
            return None
        remind_time = self._get_next_weekday_time(weekday, hour, 0)
        return {
            "remind_time": remind_time,
            "remind_type": "recurring",
            "repeat_type": "weekly"
        }
    
    def _parse_weekly_hour_minute(self, match) -> Optional[Dict[str, Any]]:
        """解析每周X点Y分"""
        weekday = self.weekday_map.get(match.group(1))
        hour = int(match.group(2))
        minute = int(match.group(3))
        if weekday is None:
            return None
        remind_time = self._get_next_weekday_time(weekday, hour, minute)
        return {
            "remind_time": remind_time,
            "remind_type": "recurring",
            "repeat_type": "weekly"
        }
    
    def _parse_specific_datetime(self, match) -> Optional[Dict[str, Any]]:
        """解析具体日期时间 YYYY-MM-DD HH:MM"""
        year, month, day, hour, minute = map(int, match.groups())
        try:
            remind_time = datetime(year, month, day, hour, minute, tzinfo=self.timezone)
            return {
                "remind_time": remind_time,
                "remind_type": "once",
                "repeat_type": None
            }
        except ValueError:
            return None
    
    def _parse_month_day_time(self, match) -> Optional[Dict[str, Any]]:
        """解析月日时间 MM-DD HH:MM"""
        month, day, hour, minute = map(int, match.groups())
        year = self._get_current_time().year
        try:
            remind_time = datetime(year, month, day, hour, minute, tzinfo=self.timezone)
            # 如果时间已过，则设置为明年
            if remind_time <= self._get_current_time():
                remind_time = remind_time.replace(year=year + 1)
            return {
                "remind_time": remind_time,
                "remind_type": "once",
                "repeat_type": None
            }
        except ValueError:
            return None
    
    def _parse_chinese_date_time(self, match) -> Optional[Dict[str, Any]]:
        """解析中文日期时间 X月X日 HH:MM"""
        month, day, hour, minute = map(int, match.groups())
        year = self._get_current_time().year
        try:
            remind_time = datetime(year, month, day, hour, minute, tzinfo=self.timezone)
            # 如果时间已过，则设置为明年
            if remind_time <= self._get_current_time():
                remind_time = remind_time.replace(year=year + 1)
            return {
                "remind_time": remind_time,
                "remind_type": "once",
                "repeat_type": None
            }
        except ValueError:
            return None
    
    def _parse_direct_time(self, time_str: str) -> Optional[Dict[str, Any]]:
        """直接解析时间字符串"""
        try:
            # 尝试解析ISO格式
            remind_time = datetime.fromisoformat(time_str.replace(' ', 'T'))
            if remind_time.tzinfo is None:
                remind_time = self.timezone.localize(remind_time)
            return {
                "remind_time": remind_time,
                "remind_type": "once",
                "repeat_type": None
            }
        except ValueError:
            pass
        
        try:
            # 尝试解析常见格式
            for fmt in ["%Y-%m-%d %H:%M", "%m-%d %H:%M", "%H:%M"]:
                try:
                    remind_time = datetime.strptime(time_str, fmt)
                    if remind_time.tzinfo is None:
                        remind_time = self.timezone.localize(remind_time)
                    # 如果只有时间，设置为今天或明天
                    if fmt == "%H:%M":
                        if remind_time.time() <= self._get_current_time().time():
                            remind_time += timedelta(days=1)
                    return {
                        "remind_time": remind_time,
                        "remind_type": "once",
                        "repeat_type": None
                    }
                except ValueError:
                    continue
        except Exception:
            pass
        
        return None
    
    def _get_next_workday_time(self, hour: int, minute: int) -> datetime:
        """获取下一个工作日的指定时间"""
        now = self._get_current_time()
        remind_time = now.replace(hour=hour, minute=minute, second=0, microsecond=0)
        # 如果今天还没到，且是工作日，则返回今天
        if remind_time > now and remind_time.weekday() < 5:
            return remind_time
        
        # 否则找到下一个工作日
        days_ahead = 1
        while True:
            next_day = now + timedelta(days=days_ahead)
            if next_day.weekday() < 5:  # 周一到周五
                return next_day.replace(hour=hour, minute=minute, second=0, microsecond=0)
            days_ahead += 1
    
    def _get_next_weekday_time(self, weekday: int, hour: int, minute: int) -> datetime:
        """获取下一个指定星期几的指定时间"""
        now = self._get_current_time()
        remind_time = now.replace(hour=hour, minute=minute, second=0, microsecond=0)
        # 如果今天还没到，且是目标星期，则返回今天
        if remind_time > now and now.weekday() == weekday:
            return remind_time
        
        # 否则找到下一个目标星期
        days_ahead = weekday - now.weekday()
        if days_ahead <= 0:  # 目标星期已过
            days_ahead += 7
        
        next_weekday = now + timedelta(days=days_ahead)
        return next_weekday.replace(hour=hour, minute=minute, second=0, microsecond=0)
    
    def format_remind_time(self, remind_time: datetime) -> str:
        """格式化提醒时间显示"""
        return remind_time.strftime("%Y-%m-%d %H:%M:%S")
    
    
    def parse_advance_time(self, advance_str: str) -> Optional[int]:
        """
        解析提前时间字符串
        
        Args:
            advance_str: 提前时间字符串，如 "-30min", "-2h", "-1d" 或 "30min", "2h", "1d"
            
        Returns:
            提前时间（分钟），如果解析失败返回None
        """
        if not advance_str or not advance_str.strip():
            return 0
        
        advance_str = advance_str.strip().lower()
        
        # 移除开头的 - 符号（如果存在）
        if advance_str.startswith('-'):
            advance_str = advance_str[1:]
        
        # 分钟格式: 30min, 30分钟
        minute_match = re.match(r"(\d+)(?:min|分钟)", advance_str)
        if minute_match:
            return int(minute_match.group(1))
        
        # 小时格式: 2h, 2小时
        hour_match = re.match(r"(\d+)(?:h|小时)", advance_str)
        if hour_match:
            return int(hour_match.group(1)) * 60
        
        # 天格式: 1d, 1天
        day_match = re.match(r"(\d+)(?:d|天)", advance_str)
        if day_match:
            return int(day_match.group(1)) * 24 * 60
        
        # 纯数字格式（默认分钟）
        number_match = re.match(r"(\d+)", advance_str)
        if number_match:
            return int(number_match.group(1))
        
        return None
    
    def parse_time_with_advance(self, time_str: str, advance_str: str = None) -> Optional[Dict[str, Any]]:
        """
        解析时间字符串和提前时间
        
        Args:
            time_str: 时间字符串
            advance_str: 提前时间字符串
            
        Returns:
            解析结果字典，包含remind_time, advance_remind_minutes等信息
        """
        # 解析主时间
        time_result = self.parse_time(time_str)
        if not time_result:
            return None
        
        # 解析提前时间
        advance_minutes = 0
        if advance_str:
            advance_minutes = self.parse_advance_time(advance_str)
            if advance_minutes is None:
                logger.warning(f"无法解析提前时间: {advance_str}")
                return None
        
        # 添加提前时间信息
        time_result["advance_remind_minutes"] = advance_minutes
        
        return time_result

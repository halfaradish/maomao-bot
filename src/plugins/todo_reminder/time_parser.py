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
        
        # 星期中文映射（周一=0, 周二=1, ..., 周日=6）
        self.weekday_map = {
            "一": 0, "二": 1, "三": 2, "四": 3, 
            "五": 4, "六": 5, "日": 6, "天": 6
        }
        
        # 时间模式配置（注意：更具体的模式要放在前面）
        self.patterns = {
            # 重复提醒模式（放在最前面，避免与一次性提醒冲突）
            "recurring": [
                (r"每天(\d+)点(\d+)分", self._parse_daily_recurring_with_minute),
                (r"每天(\d+)点", self._parse_daily_recurring_hour_only),
                (r"工作日(\d+)点(\d+)分", self._parse_workday_recurring_with_minute),
                (r"工作日(\d+)点", self._parse_workday_recurring_hour_only),
                (r"每周([一二三四五六日天])(\d+)点(\d+)分", self._parse_weekly_recurring_with_minute),
                (r"每周([一二三四五六日天])(\d+)点", self._parse_weekly_recurring_hour_only),
                (r"每月(\d+)号(\d+)点(\d+)分", self._parse_monthly_recurring_with_minute),
                (r"每月(\d+)号(\d+)点", self._parse_monthly_recurring_hour_only),
            ],
            # 相对时间模式（注意：更具体的模式要放在前面）
            "relative": [
                (r"^(现在|立刻|立即|now)$", self._parse_immediate),  # 立即提醒，放在最前面
                (r"(\d+)小时(\d+)分钟后", self._parse_hours_minutes_later),
                (r"(\d+)分钟后", self._parse_minutes_later),
                (r"(\d+)小时后", self._parse_hours_later),
            ],
            # 绝对日期时间模式（月份-日期-几点-几分）
            "absolute_date": [
                (r"(\d+)-(\d+)-(\d+)-(\d+)", self._parse_numeric_month_day_hour_minute),
                (r"(\d+)-(\d+)-(\d+)", self._parse_numeric_month_day_hour_only),
                (r"(\d+)月(\d+)日-(\d+)点-(\d+)分", self._parse_month_day_hour_minute),
                (r"(\d+)月(\d+)日-(\d+)点", self._parse_month_day_hour_only),
                (r"(\d+)小时(\d+)分(?!后)", self._parse_hours_minutes_today),  # 当天时间点，如：5小时40分
            ],
            # 周几+几点模式（注意：下周的模式要放在"周"模式之前，因为更具体）
            "weekday_time": [
                (r"下周([一二三四五六日天])(\d+)点(\d+)分", self._parse_next_week_weekday_time_with_minute),
                (r"下周([一二三四五六日天])(\d+):(\d+)", self._parse_next_week_weekday_time_colon),
                (r"下周([一二三四五六日天])(\d+)点", self._parse_next_week_weekday_time_hour_only),
                (r"周([一二三四五六日天])(\d+)点(\d+)分", self._parse_weekday_time_with_minute),
                (r"周([一二三四五六日天])(\d+):(\d+)", self._parse_weekday_time_colon),
                (r"周([一二三四五六日天])(\d+)点", self._parse_weekday_time_hour_only),
            ],
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
                            logger.debug(f"时间解析成功: {time_str} -> {pattern_type}: {pattern}")
                            return result
                    except Exception as e:
                        logger.warning(f"时间解析失败: {time_str}, 模式: {pattern}, 错误: {e}")
                        continue
        
        # 如果所有模式都失败，尝试直接解析
        return self._parse_direct_time(time_str)
    
    def _parse_direct_time(self, time_str: str) -> Optional[Dict[str, Any]]:
        """
        直接解析时间字符串（备用方法）
        当所有模式都无法匹配时调用此方法
        可以在这里添加通用的时间解析逻辑
        """
        # TODO: 实现你的直接解析逻辑
        return None
    
    def _parse_immediate(self, match) -> Optional[Dict[str, Any]]:
        """解析立即提醒（现在、立刻、立即、now）"""
        now = self._get_current_time()
        return {
            "remind_time": now,
            "remind_type": "immediate",  # 特殊标记，表示立即提醒
            "repeat_type": None
        }
    
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
    
    def _parse_hours_minutes_later(self, match) -> Optional[Dict[str, Any]]:
        """解析X小时Y分钟后"""
        hours = int(match.group(1))
        minutes = int(match.group(2))
        now = self._get_current_time()
        remind_time = now + timedelta(hours=hours, minutes=minutes)
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
    
    def _parse_hours_minutes_today(self, match) -> Optional[Dict[str, Any]]:
        """解析X小时Y分（当天时间点），如：5小时40分表示当天5点40分"""
        hours = int(match.group(1))
        minutes = int(match.group(2))
        
        # 验证时间有效性
        if not (0 <= hours < 24 and 0 <= minutes < 60):
            return None
        
        remind_time = self._get_today_time(hours, minutes)
        return {
            "remind_time": remind_time,
            "remind_type": "once",
            "repeat_type": None
        }
    
    def _parse_weekday_time_with_minute(self, match) -> Optional[Dict[str, Any]]:
        """解析周几+几点几分格式，如：周一9点30分（仅本周，一次性提醒）"""
        weekday_cn = match.group(1)
        hour = int(match.group(2))
        minute = int(match.group(3))
        
        if weekday_cn not in self.weekday_map:
            return None
        
        weekday = self.weekday_map[weekday_cn]
        
        # 验证时间有效性
        if not (0 <= hour < 24 and 0 <= minute < 60):
            return None
        
        remind_time = self._get_this_week_weekday_time(weekday, hour, minute)
        return {
            "remind_time": remind_time,
            "remind_type": "once",
            "repeat_type": None
        }
    
    def _parse_weekday_time_colon(self, match) -> Optional[Dict[str, Any]]:
        """解析周几+冒号时间格式，如：周一9:30（仅本周，一次性提醒）"""
        weekday_cn = match.group(1)
        hour = int(match.group(2))
        minute = int(match.group(3))
        
        if weekday_cn not in self.weekday_map:
            return None
        
        weekday = self.weekday_map[weekday_cn]
        
        # 验证时间有效性
        if not (0 <= hour < 24 and 0 <= minute < 60):
            return None
        
        remind_time = self._get_this_week_weekday_time(weekday, hour, minute)
        return {
            "remind_time": remind_time,
            "remind_type": "once",
            "repeat_type": None
        }
    
    def _parse_weekday_time_hour_only(self, match) -> Optional[Dict[str, Any]]:
        """解析周几+几点格式，如：周一9点（分钟默认为0，即9:00，仅本周，一次性提醒）"""
        weekday_cn = match.group(1)
        hour = int(match.group(2))
        minute = 0  # 默认分钟为0
        
        if weekday_cn not in self.weekday_map:
            return None
        
        weekday = self.weekday_map[weekday_cn]
        
        # 验证时间有效性
        if not (0 <= hour < 24):
            return None
        
        remind_time = self._get_this_week_weekday_time(weekday, hour, minute)
        return {
            "remind_time": remind_time,
            "remind_type": "once",
            "repeat_type": None
        }
    
    def _parse_next_week_weekday_time_with_minute(self, match) -> Optional[Dict[str, Any]]:
        """解析下周几+几点几分格式，如：下周一九点30分（仅下周，一次性提醒）"""
        weekday_cn = match.group(1)
        hour = int(match.group(2))
        minute = int(match.group(3))
        
        if weekday_cn not in self.weekday_map:
            return None
        
        weekday = self.weekday_map[weekday_cn]
        
        # 验证时间有效性
        if not (0 <= hour < 24 and 0 <= minute < 60):
            return None
        
        remind_time = self._get_next_week_weekday_time(weekday, hour, minute)
        return {
            "remind_time": remind_time,
            "remind_type": "once",
            "repeat_type": None
        }
    
    def _parse_next_week_weekday_time_colon(self, match) -> Optional[Dict[str, Any]]:
        """解析下周几+冒号时间格式，如：下周一九:30（仅下周，一次性提醒）"""
        weekday_cn = match.group(1)
        hour = int(match.group(2))
        minute = int(match.group(3))
        
        if weekday_cn not in self.weekday_map:
            return None
        
        weekday = self.weekday_map[weekday_cn]
        
        # 验证时间有效性
        if not (0 <= hour < 24 and 0 <= minute < 60):
            return None
        
        remind_time = self._get_next_week_weekday_time(weekday, hour, minute)
        return {
            "remind_time": remind_time,
            "remind_type": "once",
            "repeat_type": None
        }
    
    def _parse_next_week_weekday_time_hour_only(self, match) -> Optional[Dict[str, Any]]:
        """解析下周几+几点格式，如：下周一九点（分钟默认为0，即9:00，仅下周，一次性提醒）"""
        weekday_cn = match.group(1)
        hour = int(match.group(2))
        minute = 0  # 默认分钟为0
        
        if weekday_cn not in self.weekday_map:
            return None
        
        weekday = self.weekday_map[weekday_cn]
        
        # 验证时间有效性
        if not (0 <= hour < 24):
            return None
        
        remind_time = self._get_next_week_weekday_time(weekday, hour, minute)
        return {
            "remind_time": remind_time,
            "remind_type": "once",
            "repeat_type": None
        }
    
    def _parse_month_day_hour_minute(self, match) -> Optional[Dict[str, Any]]:
        """解析月份-日期-几点-几分格式，如：1月15日-9点-30分（一次性提醒）"""
        month = int(match.group(1))
        day = int(match.group(2))
        hour = int(match.group(3))
        minute = int(match.group(4))
        
        # 验证时间有效性
        if not (1 <= month <= 12):
            return None
        if not (1 <= day <= 31):
            return None
        if not (0 <= hour < 24):
            return None
        if not (0 <= minute < 60):
            return None
        
        remind_time = self._get_month_day_time(month, day, hour, minute)
        if remind_time is None:
            return None
        
        return {
            "remind_time": remind_time,
            "remind_type": "once",
            "repeat_type": None
        }
    
    def _parse_month_day_hour_only(self, match) -> Optional[Dict[str, Any]]:
        """解析月份-日期-几点格式，如：1月15日-9点（分钟默认为0，即9:00，一次性提醒）"""
        month = int(match.group(1))
        day = int(match.group(2))
        hour = int(match.group(3))
        minute = 0  # 默认分钟为0
        
        # 验证时间有效性
        if not (1 <= month <= 12):
            return None
        if not (1 <= day <= 31):
            return None
        if not (0 <= hour < 24):
            return None
        
        remind_time = self._get_month_day_time(month, day, hour, minute)
        if remind_time is None:
            return None
        
        return {
            "remind_time": remind_time,
            "remind_type": "once",
            "repeat_type": None
        }
    
    def _parse_numeric_month_day_hour_minute(self, match) -> Optional[Dict[str, Any]]:
        """解析纯数字格式：月-日-时-分，如：2-5-8-30表示2月5日8点30分（一次性提醒）"""
        month = int(match.group(1))
        day = int(match.group(2))
        hour = int(match.group(3))
        minute = int(match.group(4))
        
        # 验证时间有效性
        if not (1 <= month <= 12):
            return None
        if not (1 <= day <= 31):
            return None
        if not (0 <= hour < 24):
            return None
        if not (0 <= minute < 60):
            return None
        
        remind_time = self._get_month_day_time(month, day, hour, minute)
        if remind_time is None:
            return None
        
        return {
            "remind_time": remind_time,
            "remind_type": "once",
            "repeat_type": None
        }
    
    def _parse_numeric_month_day_hour_only(self, match) -> Optional[Dict[str, Any]]:
        """解析纯数字格式：月-日-时，如：2-5-8表示2月5日8点（分钟默认为0，即8:00，一次性提醒）"""
        month = int(match.group(1))
        day = int(match.group(2))
        hour = int(match.group(3))
        minute = 0  # 默认分钟为0
        
        # 验证时间有效性
        if not (1 <= month <= 12):
            return None
        if not (1 <= day <= 31):
            return None
        if not (0 <= hour < 24):
            return None
        
        remind_time = self._get_month_day_time(month, day, hour, minute)
        if remind_time is None:
            return None
        
        return {
            "remind_time": remind_time,
            "remind_type": "once",
            "repeat_type": None
        }
    
    def _get_today_time(self, hour: int, minute: int) -> datetime:
        """获取当天指定时间（如果已过则为明天）"""
        now = self._get_current_time()
        # 设置为今天的时间
        today_time = now.replace(hour=hour, minute=minute, second=0, microsecond=0)
        
        # 如果时间已过，则设置为明天
        if today_time < now:
            tomorrow = now + timedelta(days=1)
            return tomorrow.replace(hour=hour, minute=minute, second=0, microsecond=0)
        
        return today_time
    
    def _get_month_day_time(self, month: int, day: int, hour: int, minute: int) -> Optional[datetime]:
        """获取指定月份和日期的指定时间（当年，如果已过则为明年）"""
        now = self._get_current_time()
        year = now.year
        
        # 尝试构建日期时间（使用localize确保时区正确）
        try:
            naive_time = datetime(year, month, day, hour, minute, 0, 0)
            target_time = self.timezone.localize(naive_time)
        except ValueError:
            # 日期无效（如2月30日）
            return None
        
        # 如果时间已过，则使用明年
        if target_time < now:
            try:
                naive_time = datetime(year + 1, month, day, hour, minute, 0, 0)
                target_time = self.timezone.localize(naive_time)
            except ValueError:
                # 即使是明年，日期仍然无效（如闰年的2月29日到非闰年）
                return None
        
        return target_time
    
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
    
    def _get_this_week_weekday_time(self, weekday: int, hour: int, minute: int) -> datetime:
        """获取本周指定星期几的指定时间（仅本周，一次性提醒）"""
        now = self._get_current_time()
        # 计算本周目标星期几的日期
        days_ahead = weekday - now.weekday()
        # 如果目标星期已过，仍然返回本周的（即过去的时间）
        # 如果是今天或未来，也返回本周的
        target_date = now + timedelta(days=days_ahead)
        return target_date.replace(hour=hour, minute=minute, second=0, microsecond=0)
    
    def _get_next_week_weekday_time(self, weekday: int, hour: int, minute: int) -> datetime:
        """获取下周指定星期几的指定时间（仅下周，一次性提醒）"""
        now = self._get_current_time()
        # 计算本周目标星期几的日期
        days_ahead = weekday - now.weekday()
        # 如果目标星期已过或还未到，都加7天到下下周
        # 如果是今天或未来的本周，也加7天到下周
        target_date = now + timedelta(days=days_ahead + 7)
        return target_date.replace(hour=hour, minute=minute, second=0, microsecond=0)
    
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
        """格式化提醒时间显示（使用友好的中文格式）"""
        # 确保时区正确
        if remind_time.tzinfo is None:
            remind_time = self.timezone.localize(remind_time)
        elif remind_time.tzinfo != self.timezone:
            remind_time = remind_time.astimezone(self.timezone)
        
        now = self._get_current_time()
        
        # 计算时间差
        time_diff = remind_time - now
        days_diff = time_diff.days
        
        # 格式化时间部分
        hour = remind_time.hour
        minute = remind_time.minute
        time_str = f"{hour:02d}:{minute:02d}"
        
        # 如果是今天
        if days_diff == 0 and remind_time.date() == now.date():
            return f"今天 {time_str}"
        # 如果是明天
        elif days_diff == 1:
            return f"明天 {time_str}"
        # 如果是后天
        elif days_diff == 2:
            return f"后天 {time_str}"
        # 如果是本周内
        elif 0 <= days_diff < 7:
            weekday_names = ["周一", "周二", "周三", "周四", "周五", "周六", "周日"]
            weekday_name = weekday_names[remind_time.weekday()]
            return f"{weekday_name} {time_str}"
        # 如果是下周内
        elif 7 <= days_diff < 14:
            weekday_names = ["周一", "周二", "周三", "周四", "周五", "周六", "周日"]
            weekday_name = weekday_names[remind_time.weekday()]
            return f"下{weekday_name} {time_str}"
        # 其他情况显示完整日期
        else:
            month = remind_time.month
            day = remind_time.day
            year = remind_time.year
            # 如果是今年，不显示年份
            if year == now.year:
                return f"{month}月{day}日 {time_str}"
            else:
                return f"{year}年{month}月{day}日 {time_str}"
    
    
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
        logger.debug(f"parse_time_with_advance: 开始解析 time_str={repr(time_str)}, advance_str={advance_str}")
        time_result = self.parse_time(time_str)
        if not time_result:
            logger.warning(f"parse_time_with_advance: parse_time 返回 None, time_str={repr(time_str)}")
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
    
    def _parse_daily_recurring_with_minute(self, match) -> Optional[Dict[str, Any]]:
        """解析每天X点X分（重复提醒）"""
        hour = int(match.group(1))
        minute = int(match.group(2))
        
        # 验证时间有效性
        if not (0 <= hour < 24 and 0 <= minute < 60):
            return None
        
        # 计算下一次提醒时间（今天或明天）
        now = self._get_current_time()
        today_time = now.replace(hour=hour, minute=minute, second=0, microsecond=0)
        
        if today_time > now:
            remind_time = today_time
        else:
            # 如果今天的时间已过，则从明天开始
            remind_time = today_time + timedelta(days=1)
        
        return {
            "remind_time": remind_time,
            "remind_type": "daily",
            "repeat_type": "daily"
        }
    
    def _parse_daily_recurring_hour_only(self, match) -> Optional[Dict[str, Any]]:
        """解析每天X点（重复提醒，分钟默认为0）"""
        hour = int(match.group(1))
        minute = 0
        
        # 验证时间有效性
        if not (0 <= hour < 24):
            return None
        
        # 计算下一次提醒时间（今天或明天）
        now = self._get_current_time()
        today_time = now.replace(hour=hour, minute=minute, second=0, microsecond=0)
        
        if today_time > now:
            remind_time = today_time
        else:
            # 如果今天的时间已过，则从明天开始
            remind_time = today_time + timedelta(days=1)
        
        return {
            "remind_time": remind_time,
            "remind_type": "daily",
            "repeat_type": "daily"
        }
    
    def _parse_workday_recurring_with_minute(self, match) -> Optional[Dict[str, Any]]:
        """解析工作日X点X分（重复提醒）"""
        hour = int(match.group(1))
        minute = int(match.group(2))
        
        # 验证时间有效性
        if not (0 <= hour < 24 and 0 <= minute < 60):
            return None
        
        # 计算下一次工作日提醒时间
        remind_time = self._get_next_workday_time(hour, minute)
        
        return {
            "remind_time": remind_time,
            "remind_type": "workday",
            "repeat_type": "workday"
        }
    
    def _parse_workday_recurring_hour_only(self, match) -> Optional[Dict[str, Any]]:
        """解析工作日X点（重复提醒，分钟默认为0）"""
        hour = int(match.group(1))
        minute = 0
        
        # 验证时间有效性
        if not (0 <= hour < 24):
            return None
        
        # 计算下一次工作日提醒时间
        remind_time = self._get_next_workday_time(hour, minute)
        
        return {
            "remind_time": remind_time,
            "remind_type": "workday",
            "repeat_type": "workday"
        }
    
    def _parse_weekly_recurring_with_minute(self, match) -> Optional[Dict[str, Any]]:
        """解析每周X点X分（重复提醒）"""
        weekday_cn = match.group(1)
        hour = int(match.group(2))
        minute = int(match.group(3))
        
        if weekday_cn not in self.weekday_map:
            return None
        
        weekday = self.weekday_map[weekday_cn]
        
        # 验证时间有效性
        if not (0 <= hour < 24 and 0 <= minute < 60):
            return None
        
        # 计算下一次指定星期几的提醒时间
        remind_time = self._get_next_weekday_time(weekday, hour, minute)
        
        return {
            "remind_time": remind_time,
            "remind_type": "weekly",
            "repeat_type": "weekly"
        }
    
    def _parse_weekly_recurring_hour_only(self, match) -> Optional[Dict[str, Any]]:
        """解析每周X点（重复提醒，分钟默认为0）"""
        weekday_cn = match.group(1)
        hour = int(match.group(2))
        minute = 0
        
        if weekday_cn not in self.weekday_map:
            return None
        
        weekday = self.weekday_map[weekday_cn]
        
        # 验证时间有效性
        if not (0 <= hour < 24):
            return None
        
        # 计算下一次指定星期几的提醒时间
        remind_time = self._get_next_weekday_time(weekday, hour, minute)
        
        return {
            "remind_time": remind_time,
            "remind_type": "weekly",
            "repeat_type": "weekly"
        }
    
    def _parse_monthly_recurring_with_minute(self, match) -> Optional[Dict[str, Any]]:
        """解析每月X号X点X分（重复提醒）"""
        day = int(match.group(1))
        hour = int(match.group(2))
        minute = int(match.group(3))
        
        # 验证时间有效性
        if not (1 <= day <= 31):
            return None
        if not (0 <= hour < 24 and 0 <= minute < 60):
            return None
        
        # 计算下一次指定日期的提醒时间
        remind_time = self._get_next_monthly_time(day, hour, minute)
        if remind_time is None:
            return None
        
        return {
            "remind_time": remind_time,
            "remind_type": "monthly",
            "repeat_type": "monthly"
        }
    
    def _parse_monthly_recurring_hour_only(self, match) -> Optional[Dict[str, Any]]:
        """解析每月X号X点（重复提醒，分钟默认为0）"""
        day = int(match.group(1))
        hour = int(match.group(2))
        minute = 0
        
        # 验证时间有效性
        if not (1 <= day <= 31):
            return None
        if not (0 <= hour < 24):
            return None
        
        # 计算下一次指定日期的提醒时间
        remind_time = self._get_next_monthly_time(day, hour, minute)
        if remind_time is None:
            return None
        
        return {
            "remind_time": remind_time,
            "remind_type": "monthly",
            "repeat_type": "monthly"
        }
    
    def _get_next_monthly_time(self, day: int, hour: int, minute: int) -> Optional[datetime]:
        """获取下一个指定日期（每月X号）的指定时间"""
        now = self._get_current_time()
        year = now.year
        month = now.month
        
        # 尝试构建本月的日期时间
        try:
            naive_time = datetime(year, month, day, hour, minute, 0, 0)
            target_time = self.timezone.localize(naive_time)
            
            # 如果本月的时间还没过，返回本月
            if target_time > now:
                return target_time
        except ValueError:
            # 本月日期无效（如2月30日），继续到下个月
            pass
        
        # 本月已过或日期无效，计算下个月
        if month == 12:
            year += 1
            month = 1
        else:
            month += 1
        
        # 处理月末情况（如1月31日 -> 2月28/29日）
        from calendar import monthrange
        last_day = monthrange(year, month)[1]
        actual_day = min(day, last_day)
        
        try:
            naive_time = datetime(year, month, actual_day, hour, minute, 0, 0)
            target_time = self.timezone.localize(naive_time)
            return target_time
        except ValueError:
            # 即使处理了月末，仍然无效（不应该发生）
            return None

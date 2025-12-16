"""
Todo提醒插件时间解析器
目前只通过 Moonshot LLM 解析时间格式，不再使用本地正则/cn2date 兜底。
"""

import json
import os
import re
from datetime import datetime, timedelta
from typing import Optional, Dict, Any, Tuple

import pytz
import requests
from nonebot import logger


class TimeParser:
    """时间解析器类（基于 LLM 的时间解析）"""
    
    def __init__(self, timezone: str = "Asia/Shanghai"):
        self.timezone = pytz.timezone(timezone)
        self.moonshot_api_key = os.getenv("MOONSHOT_API_KEY")
        self.moonshot_model = os.getenv("MOONSHOT_MODEL", "moonshot-v1-8k")
    
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

        # 仅使用 LLM 解析时间
        try:
            llm_result = self._parse_with_llm(time_str)
            if llm_result:
                return llm_result
        except Exception as e:
            logger.warning(f"LLM 解析失败: {e}")

        # LLM 解析失败时，直接返回 None，由上层给出“无法解析时间格式”的提示
        return None

    def _parse_with_llm(self, time_str: str) -> Optional[Dict[str, Any]]:
        """
        使用 Moonshot LLM 解析时间字符串，返回与本地解析一致的结构。
        返回格式：
            {
              "remind_time": datetime,
              "remind_type": "once|immediate|daily|weekly|monthly|workday",
              "repeat_type": 同 remind_type 或 None
            }
        """
        if not self.moonshot_api_key:
            logger.debug("未设置 MOONSHOT_API_KEY，跳过 LLM 解析")
            return None

        now = self._get_current_time()
        timezone_name = self.timezone.zone

        system_prompt = (
            "你是一个严格的时间解析器，把用户输入的时间表达转换为未来的具体时间。\n"
            "必须返回 JSON，包含字段：\n"
            "  next_trigger_iso: 下次触发的绝对时间，ISO8601，最好带时区偏移（例如 2025-12-16T09:00:00+08:00）。\n"
            "  remind_type: immediate|once|daily|weekly|monthly|workday 之一。\n"
            "  detail: 可选，说明解析依据。\n"
            "规则：\n"
            "1) 使用给定的当前时间和时区计算相对时间（如 明天、后天、下周一、30 分钟后）。\n"
            "2) next_trigger_iso 必须在当前时间之后（允许几秒内的立即提醒）。\n"
            "3) 只有当用户**明确**提到“每天/每日/每周/周几/每月/工作日”等重复词汇时，才可以把 remind_type 设置为 daily/weekly/monthly/workday；\n"
            "   对于“今天/明天/后天/下周三/下个月1号/某个具体日期时间”等一次性时间表达，remind_type 必须是 once。\n"
            "4) 如果用户只说日期（例如“下周三”、“下周三再见”），没有说具体几点几分，\n"
            "   你必须使用当前时间的小时和分钟作为默认时间段，例如当前是 16:27，则“下周三”解析为下周三 16:27。\n"
            "5) 如果用户说“X点”但没有说上午/下午/晚上（例如“大后天三点”、“明天四点”），\n"
            "   一律按 24 小时制的 X:00 来解析，且 X 在 1~12 时视为上午时间（如“三点”= 03:00，“十点”= 10:00），不要自动改成下午 15:00、22:00 等。\n"
            "6) 要严格区分“明天”和“后天”等相对日期，不要偷懒全部当作明天。\n"
            "7) 无法解析时返回 error 字段，内容为原因，仍是合法 JSON。\n"
        )

        user_prompt = (
            f"当前时间: {now.isoformat()}\n"
            f"时区: {timezone_name}\n"
            f"用户输入: {time_str}\n"
            "请输出 JSON，只包含 next_trigger_iso, remind_type, detail(可选), error(可选)。"
        )

        response_text = self._call_moonshot(system_prompt, user_prompt)
        if not response_text:
            return None

        try:
            data = json.loads(response_text)
        except json.JSONDecodeError as e:
            logger.warning(f"LLM 返回非 JSON，无法解析: {e}, content={response_text}")
            return None

        if data.get("error"):
            logger.warning(f"LLM 解析返回错误: {data.get('error')}")
            return None

        remind_type_raw = data.get("remind_type") or data.get("type") or data.get("mode")
        remind_type = self._normalize_remind_type(remind_type_raw)
        if not remind_type:
            logger.warning(f"LLM 返回未知 remind_type: {remind_type_raw}")
            return None

        if remind_type == "immediate":
            now_dt = self._get_current_time()
            return {
                "remind_time": now_dt,
                "remind_type": "immediate",
                "repeat_type": None,
            }

        next_iso = data.get("next_trigger_iso") or data.get("start_iso") or data.get("time")
        parsed_dt = self._parse_iso_datetime(next_iso)
        if not parsed_dt:
            logger.warning(f"LLM 返回的时间无法解析: {next_iso}")
            return None

        # 确保使用配置的时区
        if parsed_dt.tzinfo is None:
            parsed_dt = self.timezone.localize(parsed_dt)
        else:
            parsed_dt = parsed_dt.astimezone(self.timezone)

        # 如果 LLM 给了过去时间，直接回退
        if parsed_dt < now:
            logger.warning(
                f"LLM 返回的时间已过期，丢弃并回退本地解析: {parsed_dt} < {now}"
            )
            return None

        repeat_type = remind_type if remind_type in ["daily", "weekly", "monthly", "workday"] else None

        return {
            "remind_time": parsed_dt,
            "remind_type": remind_type,
            "repeat_type": repeat_type,
        }

    def _call_moonshot(self, system_prompt: str, user_prompt: str) -> Optional[str]:
        """调用 Moonshot Chat Completions 接口，返回 content 文本"""
        url = "https://api.moonshot.cn/v1/chat/completions"
        headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {self.moonshot_api_key}",
        }
        payload = {
            "model": self.moonshot_model,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            "temperature": 0.1,
            "response_format": {"type": "json_object"},
        }

        try:
            resp = requests.post(url, headers=headers, json=payload, timeout=15)
            resp.raise_for_status()
            data = resp.json()
            choices = data.get("choices") or []
            if not choices:
                logger.warning("Moonshot 返回空 choices")
                return None
            content = choices[0]["message"].get("content")
            return content
        except Exception as e:
            logger.error(f"调用 Moonshot 接口失败: {e}")
            return None

    @staticmethod
    def _parse_iso_datetime(value: Optional[str]) -> Optional[datetime]:
        """解析 ISO8601 字符串为 datetime"""
        if not value or not isinstance(value, str):
            return None
        try:
            # 兼容结尾 Z 的格式
            if value.endswith("Z"):
                value = value.replace("Z", "+00:00")
            return datetime.fromisoformat(value)
        except Exception:
            return None

    @staticmethod
    def _normalize_remind_type(remind_type_raw: Optional[str]) -> Optional[str]:
        """标准化 LLM 返回的 remind_type"""
        if not remind_type_raw:
            return None
        val = remind_type_raw.lower()
        mapping = {
            "immediate": "immediate",
            "now": "immediate",
            "once": "once",
            "single": "once",
            "one_time": "once",
            "daily": "daily",
            "everyday": "daily",
            "weekly": "weekly",
            "week": "weekly",
            "monthly": "monthly",
            "month": "monthly",
            "workday": "workday",
            "weekday": "workday",
        }
        return mapping.get(val, None)
    
    def _parse_direct_time(self, time_str: str) -> Optional[Dict[str, Any]]:
        """
        旧的本地兜底解析逻辑（基于 cn2date），已弃用。
        目前已经统一由 LLM 负责解析时间，这里仅为兼容旧版本保留方法签名。
        """
        logger.debug(f"_parse_direct_time 已弃用，不再使用本地解析: {time_str}")
        return None
    
    def _extract_time_from_string(self, time_str: str) -> Optional[Tuple[int, int]]:
        """
        从时间字符串中提取时间信息（小时和分钟）
        支持格式：两点、9点、14点30分、14:30等
        """
        # 中文数字到阿拉伯数字的映射
        chinese_numbers = {
            "零": 0, "一": 1, "二": 2, "两": 2, "三": 3, "四": 4, "五": 5,
            "六": 6, "七": 7, "八": 8, "九": 9, "十": 10,
            "十一": 11, "十二": 12, "十三": 13, "十四": 14, "十五": 15,
            "十六": 16, "十七": 17, "十八": 18, "十九": 19, "二十": 20,
            "二十一": 21, "二十二": 22, "二十三": 23
        }
        
        hour = None
        minute = 0
        
        # 匹配格式：X点Y分 或 X点（如：两点、9点、14点30分）
        # 先尝试匹配带分钟的模式
        # 注意：正则表达式中包含"两"字
        pattern_with_minute = r"([零一二两三三四五六七八九十]+|[\d]+)点([零一二两三三四五六七八九十]+|[\d]+)分"
        match = re.search(pattern_with_minute, time_str)
        if match:
            hour_str = match.group(1)
            minute_str = match.group(2)
            
            # 解析小时
            if hour_str.isdigit():
                hour = int(hour_str)
            elif hour_str in chinese_numbers:
                hour = chinese_numbers[hour_str]
            elif hour_str.startswith("十") and len(hour_str) == 2:
                # 处理"十一"到"十九"
                hour = 10 + chinese_numbers.get(hour_str[1], 0)
            elif hour_str == "十":
                hour = 10
            
            # 解析分钟
            if minute_str.isdigit():
                minute = int(minute_str)
            elif minute_str in chinese_numbers:
                minute = chinese_numbers[minute_str]
            elif minute_str.startswith("十") and len(minute_str) == 2:
                minute = 10 + chinese_numbers.get(minute_str[1], 0)
            elif minute_str == "十":
                minute = 10
            
            if hour is not None and 0 <= hour < 24 and 0 <= minute < 60:
                return (hour, minute)
        
        # 匹配格式：X点（如：两点、9点、14点）
        # 注意：正则表达式中包含"两"字
        pattern_hour_only = r"([零一二两三三四五六七八九十]+|[\d]+)点"
        match = re.search(pattern_hour_only, time_str)
        if match:
            hour_str = match.group(1)
            
            # 解析小时
            if hour_str.isdigit():
                hour = int(hour_str)
            elif hour_str in chinese_numbers:
                hour = chinese_numbers[hour_str]
            elif hour_str.startswith("十") and len(hour_str) == 2:
                hour = 10 + chinese_numbers.get(hour_str[1], 0)
            elif hour_str == "十":
                hour = 10
            
            if hour is not None and 0 <= hour < 24:
                return (hour, 0)
        
        # 匹配格式：HH:MM 或 H:MM（如：14:30、9:00）
        pattern_colon = r"(\d{1,2}):(\d{2})"
        match = re.search(pattern_colon, time_str)
        if match:
            hour = int(match.group(1))
            minute = int(match.group(2))
            if 0 <= hour < 24 and 0 <= minute < 60:
                return (hour, minute)
        
        return None
    
    def _parse_common_chinese_time(self, time_str: str) -> Optional[Dict[str, Any]]:
        """
        手动解析常见的中文时间格式（当 cn2date 无法解析时的回退方案）
        支持格式：明天两点、后天9点、今天14:30等
        """
        now = self._get_current_time()
        days_offset = 0
        hour = 0
        minute = 0
        
        # 解析相对日期
        if "明天" in time_str or "明日" in time_str:
            days_offset = 1
        elif "后天" in time_str:
            days_offset = 2
        elif "大后天" in time_str:
            days_offset = 3
        elif "今天" in time_str or "今日" in time_str:
            days_offset = 0
        elif "昨天" in time_str or "昨日" in time_str:
            days_offset = -1
        elif "前天" in time_str:
            days_offset = -2
        else:
            # 如果没有明确的相对日期，尝试使用 cn2date 解析的日期部分
            # 这里先返回 None，让调用方知道无法解析
            return None
        
        # 从字符串中提取时间信息
        time_match = self._extract_time_from_string(time_str)
        if time_match:
            hour, minute = time_match
        else:
            # 如果没有找到时间信息，默认使用当前时间
            hour = now.hour
            minute = now.minute
        
        # 计算目标日期时间
        target_date = now + timedelta(days=days_offset)
        parsed_dt = target_date.replace(hour=hour, minute=minute, second=0, microsecond=0)
        
        # 添加时区信息
        if parsed_dt.tzinfo is None:
            parsed_dt = self.timezone.localize(parsed_dt)
        elif parsed_dt.tzinfo != self.timezone:
            parsed_dt = parsed_dt.astimezone(self.timezone)
        
        logger.debug(f"手动解析中文时间成功: {time_str} -> {parsed_dt}")
        return {
            "remind_time": parsed_dt,
            "remind_type": "once",
            "repeat_type": None
        }
    
    def _parse_immediate(self, match) -> Optional[Dict[str, Any]]:
        """解析立即提醒（现在、立刻、立即、now）"""
        now = self._get_current_time()
        return {
            "remind_time": now,
            "remind_type": "immediate",  # 特殊标记，表示立即提醒
            "repeat_type": None
        }
    
    def _parse_seconds_later(self, match) -> Optional[Dict[str, Any]]:
        """解析X秒后"""
        seconds = int(match.group(1))
        now = self._get_current_time()
        remind_time = now + timedelta(seconds=seconds)
        return {
            "remind_time": remind_time,
            "remind_type": "once",
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
    
    def _parse_days_hours_later(self, match) -> Optional[Dict[str, Any]]:
        """解析X天Y小时后"""
        days = int(match.group(1))
        hours = int(match.group(2))
        now = self._get_current_time()
        remind_time = now + timedelta(days=days, hours=hours)
        return {
            "remind_time": remind_time,
            "remind_type": "once",
            "repeat_type": None
        }
    
    def _parse_days_hours_minutes_later(self, match) -> Optional[Dict[str, Any]]:
        """解析X天Y小时Z分钟后"""
        days = int(match.group(1))
        hours = int(match.group(2))
        minutes = int(match.group(3))
        now = self._get_current_time()
        remind_time = now + timedelta(days=days, hours=hours, minutes=minutes)
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
        
        # 始终显示具体日期 + 周几，不使用“今天/明天/后天”等相对描述
        month = remind_time.month
        day = remind_time.day
        year = remind_time.year
        weekday_names = ["周一", "周二", "周三", "周四", "周五", "周六", "周日"]
        weekday_name = weekday_names[remind_time.weekday()]

        # 如果是今年，只显示月日；否则显示完整年月日
        if year == now.year:
            return f"{month}月{day}日 {weekday_name} {time_str}"
        else:
            return f"{year}年{month}月{day}日 {weekday_name} {time_str}"
    
    
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

"""
Todo提醒插件时间解析器
目前只通过 Moonshot LLM 解析时间格式，不再使用本地正则/cn2date 兜底。
"""

import json
import os
import re
from datetime import datetime
from typing import Optional, Dict, Any

import pytz
import requests
from nonebot import logger


class TimeParser:
    """时间解析器类（基于 LLM 的时间解析）"""

    def __init__(self, timezone: str = "Asia/Shanghai"):
        self.timezone = pytz.timezone(timezone)
        self.moonshot_api_key = os.getenv("MOONSHOT_API_KEY")
        self.moonshot_model = os.getenv("MOONSHOT_MODEL", "moonshot-v1-8k")
        self.last_usage: Optional[Dict[str, Any]] = None  # 记录最近一次 LLM 调用的 token 用量

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
        使用 Moonshot LLM 解析时间字符串。
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
                f"LLM 返回的时间已过期，丢弃: {parsed_dt} < {now}"
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
            # 记录并输出本次调用的 token 消耗，便于测试
            self.last_usage = data.get("usage")
            if self.last_usage:
                logger.info(
                    f"[todo_reminder] Moonshot token usage: "
                    f"prompt={self.last_usage.get('prompt_tokens')}, "
                    f"completion={self.last_usage.get('completion_tokens')}, "
                    f"total={self.last_usage.get('total_tokens')}"
                )
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

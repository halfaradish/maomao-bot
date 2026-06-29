import httpx
import json
from datetime import date, datetime
from typing import Dict, Any, List
from nonebot import logger, get_driver, get_plugin_config

# Import plugin config for custom_holiday_enabled toggle
from .config import Config as PluginConfig
from dataclasses import dataclass

# 全局客户端变量
client: httpx.AsyncClient | None = None
driver = get_driver()
base_url = "https://api.jiejiariapi.com/v1/holidays/"


@driver.on_startup
async def _init_client():
    global client
    # 检查客户端是否存在且未关闭，如果需要则创建新实例
    if client is None or client.is_closed:
        client = httpx.AsyncClient(timeout=10.0)

@driver.on_shutdown
async def _close_client():
    global client
    if client:
        await client.aclose()
        client = None

@dataclass
class HolidayInfo:
    # 具体的日期（格式 YYYY-MM-DD）
    date: date
    # 节日名称（如"春节"、"国庆节"）
    name: str
    # true: 代表休息日（放假）。false: 代表工作日（通常用于节前/节后的调休补班）
    is_off_day: bool

    @classmethod
    def from_dict(cls, data: Dict[str, Any]):
        """从字典创建HolidayInfo实例，提供类型安全的转换"""
        try:
            return cls(
                date = datetime.strptime(data.get('date', ''), "%Y-%m-%d").date(),
                name = str(data.get('name', '')),
                is_off_day = bool(data.get('isOffDay', True))
            )
        except (ValueError, TypeError) as e:
            logger.error(f"字段类型转换失败: {e}")
            raise


_plugin_config = get_plugin_config(PluginConfig)

holidays: List[HolidayInfo] = []


async def _reload_holidays_info():
    """从 API 和数据库重新加载节假日数据，数据库优先覆盖同日期 API 数据。"""
    global client, holidays
    # 确保客户端已初始化
    if not client or client.is_closed:
        await _init_client()

    holidays.clear()
    loaded_years = 0

    cur_year = datetime.now().year
    years_to_fetch = [cur_year, cur_year + 1]

    # ============================================================
    # Step 1: 从 API 获取节假日数据
    # ============================================================
    api_holidays: dict[date, HolidayInfo] = {}

    for year in years_to_fetch:
        url = f"{base_url}{year}"
        try:
            response = await client.get(url, timeout=httpx.Timeout(5.0, read=15.0))
            response.raise_for_status()

            data = response.json()
            for info in data.values():
                holiday = HolidayInfo.from_dict(info)
                api_holidays[holiday.date] = holiday
            logger.info(f"成功加载{year}年节假日数据")
            loaded_years += 1

        except httpx.HTTPStatusError as e:
            logger.error(f"请求节假日API失败（状态码错误）: {e}")
        except (httpx.RequestError, json.JSONDecodeError) as e:
            logger.error(f"请求节假日API发生网络或数据解析错误: {e}")
        except Exception as e:
            logger.error(f"加载节假日数据时发生未知错误: {e}")

    # ============================================================
    # Step 2: 从数据库加载自定义节假日
    # ============================================================
    db_holidays: dict[date, HolidayInfo] = {}

    if _plugin_config.custom_holiday_enabled:
        try:
            from ...common.database import async_session_factory
            from ...common.models import CustomHoliday
            from sqlalchemy import select

            async with async_session_factory() as session:
                result = await session.execute(
                    select(CustomHoliday).where(CustomHoliday.is_enabled)
                )
                custom_rows = result.scalars().all()

            for row in custom_rows:
                db_holidays[row.date] = HolidayInfo(
                    date=row.date,
                    name=row.name,
                    is_off_day=row.is_off_day,
                )
            logger.info(f"从数据库加载了 {len(db_holidays)} 条自定义节假日")
        except Exception as e:
            logger.warning(f"从数据库加载自定义节假日失败，将仅使用 API 数据: {e}")

    # ============================================================
    # Step 3: 合并 — 数据库覆盖同日期 API 数据
    # ============================================================
    merged = {**api_holidays, **db_holidays}

    if merged:
        holidays = sorted(merged.values(), key=lambda x: x.date)
        overlap_count = len(set(db_holidays.keys()) & set(api_holidays.keys()))
        new_count = len(set(db_holidays.keys()) - set(api_holidays.keys()))
        logger.info(
            f"节假日数据加载完成: "
            f"API {len(api_holidays)} 条, "
            f"数据库覆盖 {overlap_count} 条, "
            f"数据库新增 {new_count} 条, "
            f"合计 {len(holidays)} 条"
        )
    else:
        logger.warning("未能加载任何节假日数据")


async def get_holidays(force_reload: bool = False) -> List[HolidayInfo]:
    """获取节假日列表。

    Args:
        force_reload: 是否强制重新加载（忽略缓存）。

    Returns:
        节假日信息列表，按日期升序排列。
    """
    global holidays
    if force_reload or not holidays:
        await _reload_holidays_info()
        if not holidays:
            logger.warning("未能成功加载节假日数据，请检查日志。")

    return holidays

import httpx
import json
from datetime import date, datetime
from typing import Dict, Any, List
from nonebot import logger, get_driver
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
    # 节日名称（如“春节”、“国庆节”）
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

holidays: List[HolidayInfo] = []
async def _reload_holidays_info() -> bool:
    global client, holidays
    # 确保客户端已初始化
    if not client or client.is_closed:
        await _init_client()

    holidays.clear()

    cur_year = datetime.now().year
    years_to_fetch = [cur_year, cur_year + 1]

    for year in years_to_fetch:
        url = f"{base_url}{year}"
        try:
            response = await client.get(url, timeout=httpx.Timeout(5.0, read=15.0))
            response.raise_for_status()

            data = response.json()
            for info in data.values():
                holidays.append(HolidayInfo.from_dict(info))
            logger.info(f"成功加载{year}年节假日数据")

        except httpx.HTTPStatusError as e:
            logger.error(f"请求节假日API失败（状态码错误）: {e}")
            return False
        except (httpx.RequestError, json.JSONDecodeError) as e:
            logger.error(f"请求节假日API发生网络或数据解析错误: {e}")
            return False
        except Exception as e:
            logger.error(f"加载节假日数据时发生未知错误: {e}")
            return False
    
    holidays.sort(key=lambda x: x.date)
    return True
    
async def get_holidays() -> List[HolidayInfo]:
    global holidays
    if not holidays:
        success = await _reload_holidays_info()
        if not success:
            logger.warning("未能成功加载节假日数据，请检查日志。")
    
    return holidays
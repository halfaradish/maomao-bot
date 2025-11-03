from pydantic import BaseModel


class Config(BaseModel):
    """限速器插件配置"""
    # 是否启用限速
    enabled: bool = True
    # 桶容量（允许突发发送的最大数量）
    capacity: int = 5
    # 令牌补充速率（个/秒）
    refill_rate: float = 2.0
    # 是否按群限速（True=按群限速，False=全局限速）
    per_group: bool = False
    # 紧急停止开关
    emergency_stop: bool = False
    # 单个群连续发送超过此数量时自动紧急停止
    auto_stop_threshold: int = 20
    # 时间窗口（秒），在此时间内连续发送才会触发自动停止
    auto_stop_time_window: int = 60


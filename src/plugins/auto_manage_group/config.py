from pydantic import BaseModel


class Config(BaseModel):
    """Plugin Config Here"""
    data_filename: str = "auto_manage_group.json"
    context_erase_time_range: int = 30 # 上下文时间范围（秒），默认5分钟
    context_erase_delay: int = 5  # 延迟执行时间（秒），默认5秒
    context_erase_retry_delay: float = 0.1  # 撤回间隔延迟（秒），默认0.5秒
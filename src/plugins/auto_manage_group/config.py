from pydantic import BaseModel


class Config(BaseModel):
    """Plugin Config Here

    data_filename 已废弃 — 群列表（monitored_groups / ban_words_monitored_groups /
    ban_words_remind_groups）已迁移到权限系统的 GroupPermBinding 机制。
    """
    context_erase_time_range: int = 30  # 上下文时间范围（秒），默认 30 秒
    context_erase_delay: int = 5  # 延迟执行时间（秒），默认 5 秒
    context_erase_retry_delay: float = 0.1  # 撤回间隔延迟（秒），默认 0.1 秒

    auto_manage_banned_word_enable: bool = False
    auto_manage_increase: bool = False
    auto_manage_decrease: bool = False

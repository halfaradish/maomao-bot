"""
超级管理员判断

读取 NoneBot 内置的 SUPERUSERS 配置，与现有插件（group_manager 等）行为一致。
"""
from nonebot import get_driver


def is_superuser(user_id: int) -> bool:
    """检查 user_id 是否在 bot 配置的超级管理员列表中"""
    driver = get_driver()
    return str(user_id) in driver.config.superusers

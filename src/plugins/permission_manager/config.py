"""权限管理面板插件配置"""
from pydantic import BaseModel


class Config(BaseModel):
    """权限管理面板插件配置"""

    perm_mgr_command: str = "权限"
    perm_mgr_priority: int = 5
    perm_mgr_block: bool = True

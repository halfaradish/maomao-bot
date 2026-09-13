from dataclasses import dataclass
from enum import Enum
from typing import Optional

class PluginGroupEnum(Enum):
    BASE = "基础命令"
    GROUP_MANAGE = "群管理"
    CONTEST = "竞赛相关"
    UTILITY = "实用工具"
    MONITOR = "监控提醒"

class PluginBadgeColor(Enum):
    GREEN = "green"
    BLUE = "blue"
    YELLOW = "yellow"

@dataclass(eq=False)
class PluginUsageInfo:
    # 插件名称
    name: str
    # 插件功能介绍
    description: str
    # 插件使用方法
    usage: str
    # 插件组别
    group: str | None
    # 模块名
    module_name: str
    # 颜色点
    badge_color: str | None = None
    #插件id
    id: Optional[int] = None
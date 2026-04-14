from dataclasses import dataclass
from enum import Enum

class PluginGroupEnum(Enum):
    BASE = "基础命令"
    GROUP_MANAGE = "群管理"
    CONTEST = "竞赛相关"

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
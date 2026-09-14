from pydantic import BaseModel
from nonebot import get_plugin_config


class Config(BaseModel):
    """插件使用统计 配置"""

    # 总开关；生产/测试共用数据库时建议仅生产环境开启
    plugin_usage_stats_enable: bool = False
    # 排除的插件短名（逗号分隔），命中的插件触发不计入统计
    plugin_usage_stats_excluded: str = "plugin_usage_stats,logging_info"
    # 查询榜单默认条数上限
    plugin_usage_stats_top_n: int = 15
    # 使用明细保留天数（超过后每日 05:00 自动清理）
    plugin_usage_stats_retention_days: int = 365


plugin_config = get_plugin_config(Config)


def excluded_plugins() -> set[str]:
    return {p.strip() for p in plugin_config.plugin_usage_stats_excluded.split(",") if p.strip()}

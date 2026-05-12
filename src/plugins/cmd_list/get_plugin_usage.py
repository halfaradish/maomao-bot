from nonebot import get_loaded_plugins, logger
from nonebot.plugin.model import Plugin
from typing import Optional, List

from src.common.model.model import PluginUsageInfo

help_usages: Optional[List[PluginUsageInfo]] = None

def _load_help_usage():
    global help_usages
    try:
        plugins: set[Plugin] = get_loaded_plugins()

        temp_usages = []

        for plugin in plugins:
            # 获取插件元信息
            metadata = plugin.metadata
            if metadata is None:
                continue

            pg_name = metadata.name
            pg_module_name = plugin.module_name
            pg_description = metadata.description
            pg_usage = metadata.usage
            pg_badge_color = metadata.extra.get('badge_color', None)
            pg_group = metadata.extra.get('group', None)
            pg_info = PluginUsageInfo(
                name=pg_name,
                module_name=pg_module_name,
                description=pg_description,
                usage=pg_usage,
                group=pg_group if pg_group is not None else None,
                badge_color=pg_badge_color
            )
            temp_usages.append(pg_info)

            help_usages = sorted(temp_usages, key=lambda x: (x.group or "", x.name))

    except Exception as e:
        logger.info(e)

def get_help_usage() -> List[PluginUsageInfo] | None:
    global help_usages
    if help_usages is None:
        _load_help_usage()
    
    return help_usages

def get_plugin_detail(plugin_name: Optional[str]) -> Optional[PluginUsageInfo]:
    if not plugin_name:
        return None
        
    # 确保数据已加载
    all_usages = get_help_usage()
    
    if not all_usages:
        return None
    
    for plugin_info in all_usages:
        if plugin_info.name == plugin_name:
            return plugin_info
            
    return None
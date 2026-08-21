from src.common.permission import register_perm_point

register_perm_point("sub_records:use", "过题统计使用", "允许使用 过题 命令查看过题排名", plugin_name="sub_records")
register_perm_point("sub_records:notify", "过题统计推送", "定时推送过题排名的目标群", plugin_name="sub_records")

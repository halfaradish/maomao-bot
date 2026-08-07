from src.common.permission import register_perm_point

register_perm_point("check_up:use", "考勤使用", "允许使用 考勤 命令查看考勤数据", plugin_name="check_up")
register_perm_point("check_up:notify", "考勤推送", "定时推送考勤信息的目标群", plugin_name="check_up")

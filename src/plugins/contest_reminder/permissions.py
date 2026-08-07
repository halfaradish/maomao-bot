from src.common.permission import register_perm_point

register_perm_point(
    "contest_reminder:notify",
    "比赛提醒推送",
    "比赛提醒定时推送的目标群",
    plugin_name="contest_reminder",
)

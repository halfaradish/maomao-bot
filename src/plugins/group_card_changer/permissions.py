from src.common.permission import register_perm_point

register_perm_point(
    "group_card_changer:auto_update",
    "群昵称自动更新",
    "定时更新机器人昵称的目标群",
    plugin_name="group_card_changer",
)

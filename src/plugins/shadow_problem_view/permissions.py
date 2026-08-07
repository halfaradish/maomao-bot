from src.common.permission import register_perm_point

register_perm_point(
    "shadow_problem_view:notify",
    "影子过题推送",
    "影子过题定时推送的目标群",
    plugin_name="shadow_problem_view",
)

from src.common.permission import register_perm_point

register_perm_point("like:subscribe", "订阅赞", "订阅每日自动点赞功能", plugin_name="like")
register_perm_point("like:banned", "点赞黑名单", "被禁用赞我/赞他功能的群", plugin_name="like")

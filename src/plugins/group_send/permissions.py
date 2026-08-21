from src.common.permission import register_perm_point

register_perm_point("group_send:use", "分组发送", "允许使用分组发送命令向指定分组成员转发消息", plugin_name="group_send")

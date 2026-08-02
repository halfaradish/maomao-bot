from src.common.permission import register_perm_point

register_perm_point("shit_transport:use", "搬史使用", "允许在群内使用搬史命令（可发送群）", plugin_name="shit_transport")
register_perm_point("shit_transport:receive", "搬史接收", "接收搬史转发消息的群", plugin_name="shit_transport")

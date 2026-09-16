"""谛听部署 —— 权限点声明

键名遵循 ``plugin_name:action`` 约定，启动时由权限系统自动同步进数据库，
无需手工建表或播种。超级管理员天然放行（checker 的第 0 步，绕过全部检查）。
"""
from src.common.permission import register_perm_point

register_perm_point(
    "diting_deploy:pull",
    "拉取代码",
    "从远端拉取配置的分支并触发热重载",
    plugin_name="diting_deploy",
)
register_perm_point(
    "diting_deploy:build",
    "拉取并重建",
    "拉取代码、按需重建 Docker 镜像并重启服务",
    plugin_name="diting_deploy",
)
register_perm_point(
    "diting_deploy:restart",
    "重启服务",
    "不拉取代码，直接重启服务并探活",
    plugin_name="diting_deploy",
)
register_perm_point(
    "diting_deploy:view",
    "查看部署状态",
    "查看部署状态与执行日志（只读）",
    plugin_name="diting_deploy",
)

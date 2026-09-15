"""
谛听部署 —— 插件入口

通过 QQ 命令让**宿主机**上的 ``diting-agent`` 执行 git / docker 操作：

* 容器里没有 git、没有 docker CLI、没有 .git、没有 docker.sock（见 .dockerignore 与 Dockerfile），
  所以插件本身只做「鉴权 → 受理 → 回报」，真正的操作落在宿主机执行器上；
* 两边通过已经是 bind mount 的 ``data/deploy/`` 目录交换 JSON，契约见 ``protocol.py``；
* ``pull`` 之后靠 ``bot.py`` 的热重载生效，执行器会用 ``boot.json`` 校验 worker 是否真的起来了。
"""
import os

from nonebot import get_plugin_config
from nonebot.plugin import PluginMetadata

from src.common.plugin_meta import PluginBadgeColor, PluginGroupEnum

from . import permissions  # noqa: F401 — 注册权限点到权限系统
from .config import Config

# 插件启停开关：与 group_sentinel 一致，禁用时只给存根元数据，不注册任何 handler
DITING_DEPLOY_ENABLED = os.getenv("DITING_DEPLOY_ENABLED", "true").lower() == "true"

if not DITING_DEPLOY_ENABLED:
    __plugin_meta__ = PluginMetadata(
        name="谛听部署（已禁用）",
        description="通过 QQ 命令拉取代码 / 重建服务（当前已禁用，设置 DITING_DEPLOY_ENABLED=true 启用）",
        usage="此插件已在环境变量中禁用",
        supported_adapters={"~onebot.v11"},
        extra={
            "group": PluginGroupEnum.UTILITY.value,
            "badge_color": PluginBadgeColor.YELLOW.value,
        },
    )
else:
    __plugin_meta__ = PluginMetadata(
        name="谛听部署",
        description=(
            "通过 QQ 命令让宿主机 agent 拉取代码 / 重建 Docker 镜像并重启服务，"
            "pull 配合热重载使用"
        ),
        usage=(
            "/diting pull —— 拉取远端分支，靠热重载生效\n"
            "/diting build —— 拉取 → 按需重建镜像 → 重启 → 探活（需确认）\n"
            "/diting restart —— 不拉代码，直接重启并探活（需确认）\n"
            "/diting status —— 查看 agent 心跳、代码版本、容器与任务状态\n"
            "/diting log [job_id] —— 查看执行日志尾部\n"
            "注：命令名不用自己加前缀，COMMAND_START 会自动补 —— dev 环境（COMMAND_START=[\"dev-\"]）"
            "直接输入 dev-diting <子命令>，prod 环境是 /diting <子命令>"
        ),
        config=Config,
        supported_adapters={"~onebot.v11"},
        extra={
            "group": PluginGroupEnum.UTILITY.value,
            "badge_color": PluginBadgeColor.YELLOW.value,
        },
    )

    plugin_config = get_plugin_config(Config)

    from . import commands  # noqa: F401,E402 — 注册命令 matcher 与启动钩子

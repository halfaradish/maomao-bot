"""
谛听部署 —— 插件配置

⚠️ 字段名必须带 ``diting_deploy_`` 前缀：``get_plugin_config`` 把字段名直接大写成
环境变量名去读，字段叫 ``branch`` 就会去读通用的 ``BRANCH``。前缀是强制的。
"""
from pydantic import BaseModel


class Config(BaseModel):
    # pull/build 的目标分支。空值表示未配置，所有改动工作区的子命令都会被拒绝 ——
    # 这条是刻意的 fail-safe：宁可命令不生效，也不要拉错分支。
    diting_deploy_branch: str = ""

    # 命令名。**保持默认 diting，不要自己加前缀** —— COMMAND_START 会自动补：
    # prod（["/", ""]）得到 /diting 与 diting，dev（["dev-"]）得到 dev-diting。
    # 若这里填 "dev-diting"，实际注册的命令会变成 "dev-dev-diting"（前缀被拼两次），
    # 而且命令不匹配时机器人完全静默，很难查。启动时会检查并打 warning。
    diting_deploy_cmd: str = "diting"

    diting_deploy_priority: int = 5
    diting_deploy_block: bool = True

    # 队列根目录，留空则用 ${DATA_DIR}/deploy（与宿主机执行器约定一致）
    diting_deploy_queue_dir: str = ""

    # 二次确认令牌有效期（秒）
    diting_deploy_confirm_ttl: int = 60
    # 同一用户的改动类命令冷却（秒）
    diting_deploy_user_cooldown: int = 30
    # 等待宿主机执行器认领作业的上限（秒），超时明确回报「agent 未响应」
    diting_deploy_accept_timeout: int = 90
    # 要求 state.json 心跳不早于该秒数；0 表示不要求
    diting_deploy_require_agent_fresh: int = 600
    # /diting log 默认返回的日志尾部行数
    diting_deploy_log_tail_lines: int = 40
    # 非 0 时把全部部署事件额外镜像到该群
    diting_deploy_notify_group: int = 0
    # 启动时自动创建的权限组名（超管用 perm 绑定 群 <群号> <该名> 即可授权）
    diting_deploy_perm_group: str = "diting_deploy"

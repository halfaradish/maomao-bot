from typing import List

from pydantic import BaseModel, Field


class Config(BaseModel):
    """
    群聊禁言插件配置
    """

    # ban/unban 指令相关
    # 修改默认值为 auth 前缀，以匹配新的测试需求
    group_ban_cmd: str = "authban"
    group_unban_cmd: str = "authunban"
    group_kick_cmd: str = "authkick"
    group_authtest_cmd: str = "authtest"

    group_ban_priority: int = 10
    group_ban_block: bool = True

    # 白名单配置
    group_ban_whitelist_filename: str = "ban_whitelist.json"
    group_ban_default_group_whitelist: List[str] = Field(default_factory=list)
    group_ban_default_user_whitelist: List[str] = Field(
        default_factory=lambda: ["123456"]
    )
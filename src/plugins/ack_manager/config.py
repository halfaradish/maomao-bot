from pydantic import BaseModel, Field


class Config(BaseModel):
    """
    Ack 插件配置（字段名需与 .env 中的变量一致）
    """

    ack_enabled: bool = Field(
        True,
        description="全员确认功能开关，false 表示禁用插件指令",
    )
    ack_command_prefix: str = Field(
        "!ACK",
        description="触发 ACK 的前缀",
    )
    ann_command_prefix: str = Field(
        "!ANN",
        description="触发 ANN 的前缀",
    )

    @property
    def enabled(self) -> bool:
        return self.ack_enabled


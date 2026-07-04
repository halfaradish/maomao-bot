from pydantic import BaseModel


class Config(BaseModel):
    """Plugin Config Here

    当前为占位配置，后续可添加：
    - reject_reason: str          # 自定义拒绝理由
    - min_comment_length: int     # 验证信息最小长度
    """
    pass

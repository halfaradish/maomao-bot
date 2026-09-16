from pydantic import BaseModel


class Config(BaseModel):
    """群哨兵业务配置；SMTP 账号由公共邮件工具统一管理。"""

    group_sentinel_email_enabled: bool = False
    group_sentinel_email_subject: str = "入群申请待人工复核"
    group_sentinel_email_contact: str = "群主 QQ：1950482412"
    group_sentinel_email_html: bool = False

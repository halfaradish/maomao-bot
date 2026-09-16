"""调用公共邮件工具，持久化去重、失败记录和限流由公共工具统一处理。"""

from nonebot import logger

from src.common.email_sender import EmailSendError, send_email

from .config import Config
from .email_templates import build_pending_review_email


async def notify_pending_review(
    *,
    bot_id: str,
    group_id: int,
    user_id: int,
    request_flag: str,
    reason: str,
    config: Config,
) -> str:
    """初审未通过、申请挂起时调用；邮件错误不改变申请的待人工复核状态。"""
    if not config.group_sentinel_email_enabled:
        return "disabled"
    if not request_flag:
        logger.warning("[group_sentinel] 跳过邮件通知：缺少申请标识")
        return "failed"
    attempting = False
    try:
        text, html = build_pending_review_email(
            group_id=group_id,
            reason=reason,
            contact=config.group_sentinel_email_contact,
            include_html=config.group_sentinel_email_html,
        )
        attempting = True
        result = await send_email(
            to=f"{user_id}@qq.com",
            subject=config.group_sentinel_email_subject,
            text=text,
            html=html,
            idempotency_key=f"group_sentinel:pending_review:{bot_id}:{group_id}:{request_flag}",
            rate_limit_key=f"qq:{user_id}",
        )
        return result.status
    except EmailSendError as exc:
        logger.warning(
            f"[group_sentinel] 待复核邮件发送未完成：code={exc.code} "
            f"delivery_state={exc.delivery_state}"
        )
        if exc.code == "in_progress":
            return "in_progress"
        if exc.delivery_state == "unknown":
            return "uncertain"
        if exc.code in {"rate_limited", "busy", "storage"}:
            return exc.code
    except Exception as exc:
        # 不输出异常正文，第三方异常可能包含 SMTP 凭据或邮件内容。
        logger.warning(
            f"[group_sentinel] 待复核邮件处理失败：type={type(exc).__name__}"
        )
        # 未预期异常如果发生在调用发送工具之后，也不能断言服务器未接收邮件。
        return "uncertain" if attempting else "failed"
    return "failed"


def email_status_text(status: str) -> str:
    """向群内说明发送结果；SMTP 接收不等于收件箱已经收到。"""
    return {
        "sent": "邮件通知：已提交邮件服务器（不代表已送达收件箱）",
        "partial": "邮件通知：未完全提交，请人工联系申请人",
        "disabled": "邮件通知：未启用",
        "dry_run": "邮件通知：模拟发送，未实际发信",
        "duplicate": "邮件通知：此前已提交邮件服务器，已跳过重复发送",
        "in_progress": "邮件通知：同一申请已有发送中记录，请核查记录，勿重复发送",
        "uncertain": "邮件通知：发送状态不确定，请核查记录，勿直接重发",
        "rate_limited": "邮件通知：已达到发送频率限制，本次未发送，请人工联系申请人",
        "busy": "邮件通知：发送任务已满，本次未发送，请人工联系申请人",
        "storage": "邮件通知：发送记录不可用，请核查记录后人工处理",
        "failed": "邮件通知：发送失败，请人工联系申请人",
    }.get(status, "邮件通知：状态未知，请人工联系申请人")

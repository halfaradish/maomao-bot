"""公共异步邮件工具：纯文本、HTML、附件和 SMTP TLS 传输。

在 Bot 已加载环境配置后调用 ``send_email``；也可显式传入 SMTPConfig。
不注册 NoneBot 插件，不在导入时连接 SMTP。所有阻塞操作都在线程中执行。
SMTP 接收邮件不等于最终投递成功；调度器只会重试确定未发送的临时故障。
"""

import logging
import math
import os
import re
import smtplib
import ssl
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from datetime import datetime, timezone
from email import policy
from email.headerregistry import Address
from email.message import EmailMessage
from email.utils import format_datetime, make_msgid
from typing import Literal

logger = logging.getLogger(__name__)


class EmailSendError(RuntimeError):
    """统一发送错误。code 可用于业务处理；消息不包含 SMTP 原始响应或密码。"""

    def __init__(
        self, code: str, message: str, *,
        delivery_state: Literal["not_sent", "unknown"] = "not_sent",
        retryable: bool = False,
        smtp_code: int | None = None,
        message_id: str = "",
        record_id: str = "",
    ):
        self.code = code
        self.delivery_state = delivery_state
        self.retryable = retryable
        self.smtp_code = smtp_code
        self.message_id = message_id
        self.record_id = record_id
        super().__init__(message)


class EmailConfigurationError(EmailSendError):
    def __init__(self, message: str):
        super().__init__("configuration", message)


def _env_bool(env: Mapping[str, str], key: str, default: bool) -> bool:
    value = env.get(key, str(default)).strip().lower()
    if value in {"true", "1", "yes", "on"}:
        return True
    if value in {"false", "0", "no", "off"}:
        return False
    raise EmailConfigurationError(f"{key} 必须是 true 或 false")


@dataclass(frozen=True)
class SMTPConfig:
    """全局配置，与具体插件无关。密码不出现在 repr 中。

    security 支持 ssl（通常 465）或 starttls（通常 587），始终校验证书。
    timeout 是每次 socket 操作的超时，不是整封邮件的总时限。
    """

    enabled: bool = False
    dry_run: bool = False
    host: str = "smtp.qq.com"
    port: int = 465
    security: Literal["ssl", "starttls"] = "ssl"
    username: str = ""
    password: str = field(default="", repr=False)
    from_email: str = ""
    from_name: str = "谛听机器人"
    timeout: float = 10.0
    max_message_bytes: int = 20 * 1024 * 1024

    @classmethod
    def from_env(cls, env: Mapping[str, str] | None = None) -> "SMTPConfig":
        """只读取环境变量；项目的 .env 加载仍由 src.config 负责。"""
        env = os.environ if env is None else env
        if not _env_bool(env, "EMAIL_ENABLED", False):
            # 禁用时不要求其他 SMTP 配置有效，也不影响调用方的业务流程。
            return cls()
        security = env.get("SMTP_SECURITY", "ssl").strip().lower()
        try:
            port = int(env.get("SMTP_PORT") or ("465" if security == "ssl" else "587"))
            timeout = float(env.get("SMTP_TIMEOUT") or "10")
            max_bytes = int(env.get("EMAIL_MAX_MESSAGE_BYTES") or str(20 * 1024 * 1024))
        except ValueError:
            raise EmailConfigurationError("SMTP_PORT、SMTP_TIMEOUT、EMAIL_MAX_MESSAGE_BYTES 必须是数值") from None
        return cls(
            enabled=True,
            dry_run=_env_bool(env, "EMAIL_DRY_RUN", False),
            host=env.get("SMTP_HOST", "smtp.qq.com").strip(),
            port=port,
            security=security,
            username=env.get("SMTP_USERNAME", "").strip(),
            password=env.get("SMTP_PASSWORD", ""),
            from_email=env.get("SMTP_FROM_EMAIL", "").strip(),
            from_name=env.get("SMTP_FROM_NAME", "谛听机器人"),
            timeout=timeout,
            max_message_bytes=max_bytes,
        )

    def validate(self) -> None:
        if not self.host or any(c.isspace() or ord(c) < 32 for c in self.host):
            raise EmailConfigurationError("SMTP_HOST 无效")
        if self.security not in {"ssl", "starttls"}:
            raise EmailConfigurationError("SMTP_SECURITY 必须为 ssl 或 starttls")
        if not 1 <= self.port <= 65535:
            raise EmailConfigurationError("SMTP_PORT 必须在 1 到 65535 之间")
        if not math.isfinite(self.timeout) or self.timeout <= 0:
            raise EmailConfigurationError("SMTP_TIMEOUT 必须为正的有限数值")
        if self.max_message_bytes <= 0:
            raise EmailConfigurationError("EMAIL_MAX_MESSAGE_BYTES 必须为正整数")
        if not (self.from_email or self.username):
            raise EmailConfigurationError("必须设置 SMTP_FROM_EMAIL 或 SMTP_USERNAME")
        if not self.dry_run and not (self.username and self.password):
            raise EmailConfigurationError("必须设置 SMTP_USERNAME 和 SMTP_PASSWORD（邮箱授权码）")


@dataclass(frozen=True)
class EmailAttachment:
    """内存中的附件；content_id 设置后为 HTML 中 cid:ID 引用的内嵌图片。

    调用方负责读取数据，本工具不会按用户提供的路径读取文件。
    """

    filename: str
    data: bytes = field(repr=False)
    content_type: str = "application/octet-stream"
    content_id: str | None = None


@dataclass(frozen=True)
class EmailSendResult:
    """sent/partial 表示 SMTP 接收结果；disabled/dry_run 均未连接服务器。"""

    status: Literal["sent", "partial", "disabled", "dry_run", "duplicate"]
    message_id: str = ""
    accepted: tuple[str, ...] = field(default=(), repr=False)
    refused: tuple[str, ...] = field(default=(), repr=False)
    refused_codes: tuple[tuple[str, int | None], ...] = field(default=(), repr=False)
    record_id: str = ""


def _header(value: str, name: str) -> str:
    if not isinstance(value, str) or any(ord(c) < 32 or ord(c) == 127 for c in value):
        raise EmailSendError("message", f"{name} 必须为不含换行或控制字符的字符串")
    return value


def _address(value: str) -> str:
    """仅接收单个裸邮箱地址；显示名由 from_name 单独传入。"""
    value = _header(value, "邮箱地址").strip()
    try:
        address = Address(addr_spec=value)
        if not address.username or not address.domain or any(c.isspace() for c in value):
            raise ValueError
        # 允许国际化域名；非 ASCII 的邮箱本地部分需要 SMTPUTF8，本版本不接收。
        address.username.encode("ascii")
        domain = address.domain.encode("idna").decode("ascii").lower()
        return Address(username=address.username, domain=domain).addr_spec
    except (ValueError, IndexError, UnicodeError):
        raise EmailSendError("message", "邮箱地址格式无效（请传入单个 name@example.com）") from None


def _addresses(values: str | Sequence[str]) -> tuple[str, ...]:
    if isinstance(values, str):
        values = [values]
    return tuple(dict.fromkeys(_address(value) for value in values))


def _build_message(
    config: SMTPConfig,
    to: str | Sequence[str],
    subject: str,
    text: str | None,
    html: str | None,
    cc: str | Sequence[str],
    bcc: str | Sequence[str],
    reply_to: str | None,
    attachments: Sequence[EmailAttachment],
) -> tuple[EmailMessage, str, tuple[str, ...]]:
    sender = _address(config.from_email or config.username)
    to_addresses, cc_addresses, bcc_addresses = _addresses(to), _addresses(cc), _addresses(bcc)
    recipients = tuple(dict.fromkeys((*to_addresses, *cc_addresses, *bcc_addresses)))
    if not recipients:
        raise EmailSendError("message", "至少需要一个收件人")
    if not (text or html):
        raise EmailSendError("message", "必须提供 text 或 html 正文")

    message = EmailMessage(policy=policy.SMTP)
    message["From"] = Address(display_name=_header(config.from_name, "发件人名称"), addr_spec=sender)
    if to_addresses:
        message["To"] = ", ".join(to_addresses)
    if cc_addresses:
        message["Cc"] = ", ".join(cc_addresses)
    # Bcc 仅放入 SMTP 信封，不进入邮件头，防止密送地址泄漏。
    if reply_to:
        message["Reply-To"] = _address(reply_to)
    message["Subject"] = _header(subject, "邮件主题")
    message["Date"] = format_datetime(datetime.now(timezone.utc))
    message["Message-ID"] = make_msgid(domain=sender.rsplit("@", 1)[1])
    if text is not None:
        # 编码为 7-bit 安全载荷，兼容未声明 8BITMIME 的 SMTP 服务器。
        message.set_content(text, charset="utf-8", cte="quoted-printable")
        if html is not None:
            message.add_alternative(html, subtype="html", charset="utf-8", cte="quoted-printable")
    else:
        message.set_content(html, subtype="html", charset="utf-8", cte="quoted-printable")

    raw_size = len((text or "").encode("utf-8")) + len((html or "").encode("utf-8"))
    if raw_size > config.max_message_bytes:
        raise EmailSendError("message", "邮件超过 EMAIL_MAX_MESSAGE_BYTES 限制")
    html_part = message.get_body(preferencelist=("html",)) if html is not None else None
    content_ids: set[str] = set()
    regular_attachments: list[tuple[EmailAttachment, str, list[str]]] = []
    for attachment in attachments:
        filename = _header(attachment.filename, "附件名")
        if not filename or "/" in filename or "\\" in filename:
            raise EmailSendError("message", "附件名必须是文件名，不能包含目录")
        if not isinstance(attachment.data, bytes):
            raise EmailSendError("message", "附件 data 必须为 bytes")
        raw_size += len(attachment.data)
        if raw_size > config.max_message_bytes:
            raise EmailSendError("message", "邮件超过 EMAIL_MAX_MESSAGE_BYTES 限制")
        content_type = _header(attachment.content_type, "附件 MIME 类型")
        parts = content_type.split("/")
        if len(parts) != 2 or not all(parts) or any(c.isspace() or c == ";" for c in content_type):
            raise EmailSendError("message", "附件 content_type 必须为 type/subtype")
        if attachment.content_id is not None:
            content_id = _header(attachment.content_id, "内嵌图片 ID")
            if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_.@-]{0,199}", content_id):
                raise EmailSendError("message", "内嵌图片 ID 必须为不含括号的 ASCII 标识符")
            if content_id in content_ids:
                raise EmailSendError("message", "内嵌图片 ID 不能重复")
            if html_part is None or parts[0].lower() != "image":
                raise EmailSendError("message", "内嵌图片需要 HTML 正文及 image/* MIME 类型")
            content_ids.add(content_id)
            html_part.add_related(
                attachment.data, maintype=parts[0], subtype=parts[1], filename=filename,
                cid=f"<{content_id}>", disposition="inline",
            )
        else:
            regular_attachments.append((attachment, filename, parts))

    # 先组装 HTML 的 related 子树，再创建最外层 mixed，兼容仅 HTML 正文。
    for attachment, filename, parts in regular_attachments:
        message.add_attachment(attachment.data, maintype=parts[0], subtype=parts[1], filename=filename)

    if len(message.as_bytes()) > config.max_message_bytes:
        raise EmailSendError("message", "编码后的邮件超过 EMAIL_MAX_MESSAGE_BYTES 限制")
    return message, sender, recipients


def _smtp_code(value: object) -> int | None:
    """只保留数值响应码，不向日志、记录或调用方传播原始响应正文。"""
    return value if isinstance(value, int) and not isinstance(value, bool) and 100 <= value <= 599 else None


def _temporary(code: int | None) -> bool:
    return code is not None and 400 <= code < 500


def _send_sync(config: SMTPConfig, **message_args) -> EmailSendResult:
    try:
        config.validate()
        message, sender, recipients = _build_message(config, **message_args)
    except EmailSendError:
        raise
    except Exception:
        raise EmailSendError("message", "邮件构建失败，请检查参数类型及配置") from None
    message_id = str(message["Message-ID"])
    if config.dry_run:
        logger.info("[email] dry_run message_id=%s recipients=%d", message_id, len(recipients))
        return EmailSendResult("dry_run", message_id)

    client = None
    # send_message 封装 MAIL/RCPT/DATA；进入后若失去响应，无法断言服务器没收到。
    submitting = False
    try:
        context = ssl.create_default_context()
        if config.security == "ssl":
            client = smtplib.SMTP_SSL(config.host, config.port, timeout=config.timeout, context=context)
        else:
            client = smtplib.SMTP(config.host, config.port, timeout=config.timeout)
            client.ehlo()
            client.starttls(context=context)  # 不支持 STARTTLS 则失败，不降级为明文。
            client.ehlo()
        client.login(config.username, config.password)
        submitting = True
        failures = client.send_message(message, from_addr=sender, to_addrs=list(recipients))
        refused = tuple(address for address in recipients if address in failures)
        accepted = tuple(address for address in recipients if address not in failures)
        refused_codes = tuple((address, _smtp_code(failures[address][0])) for address in refused)
        result = EmailSendResult("partial" if refused else "sent", message_id, accepted, refused, refused_codes)
        logger.info("[email] status=%s message_id=%s accepted=%d refused=%d", result.status,
                    message_id, len(accepted), len(refused))
        return result
    except smtplib.SMTPAuthenticationError as exc:
        raise EmailSendError("authentication", "SMTP 身份验证失败，请检查发件账号和授权码",
                             smtp_code=_smtp_code(exc.smtp_code), message_id=message_id) from None
    except smtplib.SMTPRecipientsRefused as exc:
        codes = tuple(_smtp_code(value[0]) for value in exc.recipients.values())
        uniform_code = codes[0] if codes and len(set(codes)) == 1 else None
        raise EmailSendError("recipients_refused", "SMTP 拒绝了所有收件人",
                             retryable=bool(codes) and all(_temporary(code) for code in codes),
                             smtp_code=uniform_code, message_id=message_id) from None
    except (smtplib.SMTPSenderRefused, smtplib.SMTPDataError) as exc:
        # MAIL 或 DATA 的明确拒绝响应：本次邮件确定未被服务器接受。
        code = _smtp_code(exc.smtp_code)
        raise EmailSendError("smtp", "SMTP 服务器明确拒绝了邮件",
                             retryable=_temporary(code), smtp_code=code, message_id=message_id) from None
    except smtplib.SMTPNotSupportedError:
        raise EmailSendError("tls", "SMTP TLS 或所需功能不可用", message_id=message_id) from None
    except ssl.SSLError:
        raise EmailSendError("tls", "SMTP TLS 连接失败",
                             delivery_state="unknown" if submitting else "not_sent", message_id=message_id) from None
    except TimeoutError:
        raise EmailSendError("timeout", "SMTP 操作超时",
                             delivery_state="unknown" if submitting else "not_sent",
                             retryable=not submitting, message_id=message_id) from None
    except smtplib.SMTPServerDisconnected:
        raise EmailSendError("connection", "SMTP 连接中断",
                             delivery_state="unknown" if submitting else "not_sent",
                             retryable=not submitting, message_id=message_id) from None
    except smtplib.SMTPResponseException as exc:
        code = _smtp_code(exc.smtp_code)
        raise EmailSendError("smtp", "SMTP 服务器未接受邮件操作",
                             delivery_state="unknown" if submitting else "not_sent",
                             retryable=not submitting and _temporary(code),
                             smtp_code=code, message_id=message_id) from None
    except smtplib.SMTPException:
        raise EmailSendError("smtp", "SMTP 服务器未接受邮件操作",
                             delivery_state="unknown" if submitting else "not_sent", message_id=message_id) from None
    except OSError:
        raise EmailSendError("connection", "SMTP 网络连接失败",
                             delivery_state="unknown" if submitting else "not_sent",
                             retryable=not submitting, message_id=message_id) from None
    except Exception:
        raise EmailSendError("internal", "邮件发送发生内部错误",
                             delivery_state="unknown" if submitting else "not_sent", message_id=message_id) from None
    finally:
        if client is not None:
            # DATA 已被接收后，QUIT 失败也不能改判邮件失败或触发整封重发。
            try:
                client.quit()
            except (OSError, smtplib.SMTPException):
                pass
            finally:
                try:
                    client.close()
                except OSError:
                    pass


async def send_email(
    *,
    to: str | Sequence[str],
    subject: str,
    text: str | None = None,
    html: str | None = None,
    cc: str | Sequence[str] = (),
    bcc: str | Sequence[str] = (),
    reply_to: str | None = None,
    attachments: Sequence[EmailAttachment] = (),
    config: SMTPConfig | None = None,
    idempotency_key: str | None = None,
    rate_limit_key: str | None = None,
) -> EmailSendResult:
    """发送邮件。提供 text+html 时生成 multipart/alternative。

    失败抛 EmailSendError（不含 SMTP 原始错误文本），禁用/模拟有独立返回状态。
    调度器提供持久化记录、限流和安全重试；idempotency_key 标识同一业务通知。
    协程取消不能撤回已提交的邮件；不确定是否发出的任务不自动重试。
    HTML 内容由调用方生成，插入用户输入时必须转义；本函数不渲染业务模板。
    """
    try:
        config = config if config is not None else SMTPConfig.from_env()
        if not config.enabled:
            return EmailSendResult("disabled")
        from .email_delivery import dispatch_email

        return await dispatch_email(
            config=config,
            message_args=dict(to=to, subject=subject, text=text, html=html,
                              cc=cc, bcc=bcc, reply_to=reply_to, attachments=attachments),
            idempotency_key=idempotency_key, rate_limit_key=rate_limit_key,
        )
    except EmailSendError:
        raise
    except Exception:
        # 不传播第三方响应/异常正文，避免收件地址、正文、授权码进入调用方日志。
        raise EmailSendError("internal", "邮件构建或发送失败，请检查参数及配置",
                             delivery_state="unknown") from None

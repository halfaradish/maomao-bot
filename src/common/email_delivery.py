"""邮件调度：有界线程池、SQLite 发送记录、持久化去重与保守重试。

不保存邮件正文/附件/SMTP 凭据，不创建后台定时补发任务。
进程崩溃时未完成的 sending 记录禁止自动重发：SMTP 不支持严格 exactly-once。
"""

import asyncio
import hashlib
import json
import math
import os
import sqlite3
import threading
import time
import uuid
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, replace
from pathlib import Path

from .email_sender import EmailConfigurationError, EmailSendError, EmailSendResult


@dataclass(frozen=True)
class DeliveryConfig:
    record_db: str = "data/email_delivery.sqlite3"
    workers: int = 2
    queue_size: int = 20
    rate_count: int = 30
    rate_window: float = 60
    recipient_count: int = 3
    recipient_window: float = 3600
    retry_attempts: int = 3
    retry_delay: float = 1

    @classmethod
    def from_env(cls):
        try:
            config = cls(
                record_db=os.getenv("EMAIL_RECORD_DB", cls.record_db),
                workers=int(os.getenv("EMAIL_WORKERS", "2")),
                queue_size=int(os.getenv("EMAIL_QUEUE_SIZE", "20")),
                rate_count=int(os.getenv("EMAIL_RATE_COUNT", "30")),
                rate_window=float(os.getenv("EMAIL_RATE_WINDOW", "60")),
                recipient_count=int(os.getenv("EMAIL_RECIPIENT_RATE_COUNT", "3")),
                recipient_window=float(os.getenv("EMAIL_RECIPIENT_RATE_WINDOW", "3600")),
                retry_attempts=int(os.getenv("EMAIL_RETRY_ATTEMPTS", "3")),
                retry_delay=float(os.getenv("EMAIL_RETRY_DELAY", "1")),
            )
        except ValueError:
            raise EmailConfigurationError("邮件调度参数必须为有效数值") from None
        if not config.record_db.strip() or config.record_db == ":memory:":
            raise EmailConfigurationError("EMAIL_RECORD_DB 必须为持久化文件路径")
        if not 1 <= config.workers <= 16 or not 0 <= config.queue_size <= 1000:
            raise EmailConfigurationError("EMAIL_WORKERS 须为 1..16，EMAIL_QUEUE_SIZE 须为 0..1000")
        if config.rate_count < 1 or config.recipient_count < 1:
            raise EmailConfigurationError("邮件发送频率次数必须为正整数")
        for window in (config.rate_window, config.recipient_window):
            if not math.isfinite(window) or not 0 < window <= 365 * 86400:
                raise EmailConfigurationError("邮件限流窗口须为大于 0、不超过一年的秒数")
        if not 1 <= config.retry_attempts <= 5:
            raise EmailConfigurationError("EMAIL_RETRY_ATTEMPTS 须为 1..5（包含首次发送）")
        if not math.isfinite(config.retry_delay) or not 0 <= config.retry_delay <= 10:
            raise EmailConfigurationError("EMAIL_RETRY_DELAY 须为 0..10 秒")
        return config


def _digest(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def _key(value: str | None, name: str) -> str | None:
    if value is None:
        return None
    if not isinstance(value, str) or not value or len(value) > 2048:
        raise EmailSendError("message", f"{name} 必须为 1..2048 个字符的字符串")
    return _digest(value)


class _RateLimited(Exception):
    pass


class DeliveryStore:
    """每次操作独立连接；BEGIN IMMEDIATE 保证同一数据库内跨进程原子去重/限流。"""

    def __init__(self, path: str):
        self.path = Path(path).expanduser().resolve()
        self.path.parent.mkdir(parents=True, exist_ok=True)
        # 尽可能限制新建文件权限；不修改已有文件权限，不支持网络共享文件系统。
        descriptor = os.open(self.path, os.O_CREAT | os.O_APPEND | os.O_WRONLY, 0o600)
        os.close(descriptor)
        with self.connect() as conn:
            conn.executescript("""
                CREATE TABLE IF NOT EXISTS email_deliveries (
                    id TEXT PRIMARY KEY,
                    created_at REAL NOT NULL,
                    updated_at REAL NOT NULL,
                    status TEXT NOT NULL,
                    recipients TEXT NOT NULL,
                    message_id TEXT NOT NULL DEFAULT '',
                    attempts INTEGER NOT NULL DEFAULT 0,
                    error_code TEXT,
                    smtp_code INTEGER,
                    accepted TEXT NOT NULL DEFAULT '[]',
                    refused_codes TEXT NOT NULL DEFAULT '[]'
                );
                CREATE TABLE IF NOT EXISTS email_attempts (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    delivery_id TEXT NOT NULL,
                    started_at REAL NOT NULL,
                    finished_at REAL,
                    status TEXT NOT NULL,
                    message_id TEXT NOT NULL DEFAULT '',
                    error_code TEXT,
                    smtp_code INTEGER,
                    accepted TEXT NOT NULL DEFAULT '[]',
                    refused_codes TEXT NOT NULL DEFAULT '[]'
                );
                CREATE INDEX IF NOT EXISTS email_attempt_delivery
                    ON email_attempts(delivery_id);
                CREATE TABLE IF NOT EXISTS email_rate_events (
                    key TEXT NOT NULL,
                    created_at REAL NOT NULL,
                    expires_at REAL NOT NULL
                );
                CREATE INDEX IF NOT EXISTS email_rate_key_time
                    ON email_rate_events(key, created_at);
                CREATE INDEX IF NOT EXISTS email_rate_expiry
                    ON email_rate_events(expires_at);
            """)

    def connect(self):
        # 使用 closing 包装器确保连接本身关闭，而不仅是提交事务。
        return _Connection(self.path)

    def claim(self, delivery_id: str, recipients: tuple[str, ...]):
        now = time.time()
        with self.connect() as conn:
            conn.execute("BEGIN IMMEDIATE")
            row = conn.execute(
                "SELECT status, recipients, message_id FROM email_deliveries WHERE id = ?",
                (delivery_id,),
            ).fetchone()
            encoded = json.dumps(sorted(recipients), ensure_ascii=True)
            if row:
                status, previous_recipients, message_id = row
                if previous_recipients != encoded:
                    raise EmailSendError("key_conflict", "同一幂等标识不能用于不同收件人")
                if status in {"sent", "partial"}:
                    return EmailSendResult("duplicate", message_id, record_id=delivery_id)
                if status in {"sending", "unknown"}:
                    raise EmailSendError(
                        "in_progress" if status == "sending" else "uncertain",
                        "该邮件正在发送或上次结果不确定，请查询记录，勿直接重发",
                        delivery_state="unknown", message_id=message_id, record_id=delivery_id,
                    )
                conn.execute(
                    "UPDATE email_deliveries SET status='sending', updated_at=?, error_code=NULL, "
                    "smtp_code=NULL WHERE id=?", (now, delivery_id),
                )
            else:
                conn.execute(
                    "INSERT INTO email_deliveries(id, created_at, updated_at, status, recipients) "
                    "VALUES (?, ?, ?, 'sending', ?)", (delivery_id, now, now, encoded),
                )
        return None

    def begin_attempt(self, delivery_id: str, keys: tuple[str, ...], config: DeliveryConfig) -> int:
        now = time.time()
        limits = [("global", config.rate_count, config.rate_window)]
        limits.extend((key, config.recipient_count, config.recipient_window) for key in keys)
        with self.connect() as conn:
            conn.execute("BEGIN IMMEDIATE")
            # 每个事件记住自己的有效期，短窗口进程不能清掉其他进程的长窗口记录。
            conn.execute("DELETE FROM email_rate_events WHERE expires_at <= ?", (now,))
            for key, count, window in limits:
                used = conn.execute(
                    "SELECT COUNT(*) FROM email_rate_events WHERE key=? AND created_at>?",
                    (key, now - window),
                ).fetchone()[0]
                if used >= count:
                    raise _RateLimited
            conn.executemany("INSERT INTO email_rate_events(key, created_at, expires_at) VALUES (?, ?, ?)",
                             [(key, now, now + window) for key, _, window in limits])
            cursor = conn.execute(
                "INSERT INTO email_attempts(delivery_id, started_at, status) VALUES (?, ?, 'sending')",
                (delivery_id, now),
            )
            conn.execute("UPDATE email_deliveries SET attempts=attempts+1, updated_at=? WHERE id=?",
                         (now, delivery_id))
            return cursor.lastrowid

    def finish(self, delivery_id: str, attempt_id: int | None, *, result=None, error=None,
               retrying: bool = False):
        status = result.status if result else error.delivery_state
        message_id = result.message_id if result else error.message_id
        code = None if result else error.code
        smtp_code = None if result else error.smtp_code
        accepted = json.dumps(result.accepted if result else ())
        refused = json.dumps(result.refused_codes if result else ())
        now = time.time()
        with self.connect() as conn:
            conn.execute("BEGIN IMMEDIATE")
            if attempt_id is not None:
                conn.execute(
                    "UPDATE email_attempts SET status=?, finished_at=?, message_id=?, error_code=?, "
                    "smtp_code=?, accepted=?, refused_codes=? WHERE id=?",
                    (status, now, message_id, code, smtp_code, accepted, refused, attempt_id),
                )
            conn.execute(
                "UPDATE email_deliveries SET status=?, updated_at=?, message_id=?, error_code=?, "
                "smtp_code=?, accepted=?, refused_codes=? WHERE id=?",
                ("sending" if retrying else status, now, message_id, code, smtp_code,
                 accepted, refused, delivery_id),
            )


class _Connection:
    def __init__(self, path):
        self.conn = sqlite3.connect(path, timeout=5)

    def __enter__(self):
        return self.conn

    def __exit__(self, *args):
        try:
            return self.conn.__exit__(*args)
        finally:
            self.conn.close()


def _deliver_sync(config, message_args, settings, idempotency_key, rate_limit_key):
    from .email_sender import _addresses, _send_sync

    config.validate()
    if config.dry_run:
        return _send_sync(config, **message_args)
    recipients = tuple(dict.fromkeys(
        address for name in ("to", "cc", "bcc")
        for address in _addresses(message_args[name])
    ))
    if not recipients:
        raise EmailSendError("message", "至少需要一个收件人")
    keys = tuple(dict.fromkeys(
        ["recipient:" + _digest(address.casefold()) for address in recipients]
        + (["business:" + rate_limit_key] if rate_limit_key else [])
    ))
    delivery_id = "key:" + idempotency_key if idempotency_key else "mail:" + uuid.uuid4().hex
    may_have_sent = False
    try:
        store = DeliveryStore(settings.record_db)
        duplicate = store.claim(delivery_id, recipients)
        if duplicate:
            return duplicate
        for number in range(settings.retry_attempts):
            try:
                attempt_id = store.begin_attempt(delivery_id, keys, settings)
            except _RateLimited:
                error = EmailSendError("rate_limited", "邮件发送频率超限，本次未发出，请稍后再调用",
                                       record_id=delivery_id)
                store.finish(delivery_id, None, error=error)
                raise error
            try:
                may_have_sent = True
                result = _send_sync(config, **message_args)
            except EmailSendError as error:
                error.record_id = delivery_id
                may_have_sent = error.delivery_state != "not_sent"
                retry = (error.delivery_state == "not_sent" and error.retryable
                         and number + 1 < settings.retry_attempts)
                store.finish(delivery_id, attempt_id, error=error, retrying=retry)
                if not retry:
                    raise
                # 仅在邮件专用工作线程内退避；不会占用事件循环或默认线程池。
                time.sleep(min(settings.retry_delay * 2 ** number, 30))
            except Exception:
                error = EmailSendError("internal", "邮件发送意外中断，结果不确定",
                                       delivery_state="unknown", record_id=delivery_id)
                store.finish(delivery_id, attempt_id, error=error)
                raise error from None
            else:
                result = replace(result, record_id=delivery_id)
                store.finish(delivery_id, attempt_id, result=result)
                return result
    except (sqlite3.Error, OSError):
        raise EmailSendError(
            "storage", "邮件记录存储不可用；请检查目录权限及磁盘，不要绕过去重直接重发",
            delivery_state="unknown" if may_have_sent else "not_sent",
            record_id=delivery_id,
        ) from None


class _Runtime:
    def __init__(self, workers: int, queue_size: int):
        self.limits = (workers, queue_size)
        self.slots = threading.BoundedSemaphore(workers + queue_size)
        self.executor = ThreadPoolExecutor(max_workers=workers, thread_name_prefix="email-sender")

    def submit(self, *args):
        if not self.slots.acquire(blocking=False):
            raise EmailSendError("busy", "邮件发送队列已满，本次未发出，请稍后再调用")
        try:
            future = self.executor.submit(_deliver_sync, *args)
        except Exception:
            self.slots.release()
            raise EmailSendError("busy", "邮件发送线程池不可用，本次未发出") from None
        # 即使调用协程取消，仍由工作线程完成写记录，直到真正结束才释放容量。
        future.add_done_callback(lambda _: self.slots.release())
        return future


_runtime = None
_runtime_lock = threading.Lock()


async def dispatch_email(*, config, message_args, idempotency_key=None, rate_limit_key=None):
    global _runtime
    key = _key(idempotency_key, "idempotency_key")
    rate_key = _key(rate_limit_key, "rate_limit_key")
    # 排队后调用方可能修改原列表；固定信封和附件，确保记录与真正投递一致。
    try:
        message_args = dict(message_args)
        for name in ("to", "cc", "bcc"):
            values = message_args[name]
            message_args[name] = values if isinstance(values, str) else tuple(values)
        message_args["attachments"] = tuple(message_args["attachments"])
    except (TypeError, KeyError):
        raise EmailSendError("message", "收件人和附件参数必须为有效序列") from None
    settings = DeliveryConfig.from_env()
    with _runtime_lock:
        if _runtime is None:
            _runtime = _Runtime(settings.workers, settings.queue_size)
        if _runtime.limits != (settings.workers, settings.queue_size):
            raise EmailConfigurationError("修改 EMAIL_WORKERS/EMAIL_QUEUE_SIZE 后须重启进程")
        future = _runtime.submit(config, message_args, settings, key, rate_key)
    wrapped = asyncio.wrap_future(future)
    # 调用方取消后仍消费后台异常，避免 event loop 的未提取异常日志泄漏细节。
    wrapped.add_done_callback(lambda task: None if task.cancelled() else task.exception())
    return await asyncio.shield(wrapped)


def list_email_records(*, record_db: str | None = None, limit: int = 20,
                       recipient: str | None = None, status: str | None = None) -> list[dict]:
    """只读查询，不创建数据库、不发送邮件；返回收件地址，勿公开转发查询结果。"""
    if not 1 <= limit <= 1000:
        raise ValueError("limit 必须为 1..1000")
    path = Path(record_db or os.getenv("EMAIL_RECORD_DB", DeliveryConfig.record_db)).expanduser().resolve()
    clauses, parameters = [], []
    if recipient is not None:
        clauses.append("instr(recipients, ?) > 0")
        parameters.append(json.dumps(recipient, ensure_ascii=True))
    if status is not None:
        clauses.append("status = ?")
        parameters.append(status)
    where = " WHERE " + " AND ".join(clauses) if clauses else ""
    conn = None
    try:
        conn = sqlite3.connect(path.as_uri() + "?mode=ro", uri=True, timeout=5)
        conn.row_factory = sqlite3.Row
        rows = conn.execute("SELECT * FROM email_deliveries" + where
                            + " ORDER BY updated_at DESC LIMIT ?", (*parameters, limit)).fetchall()
        records = []
        for row in rows:
            record = dict(row)
            for name in ("recipients", "accepted", "refused_codes"):
                record[name] = json.loads(record[name])
            records.append(record)
        return records
    except (sqlite3.Error, OSError):
        raise EmailSendError("storage", "无法读取邮件记录：请确认已真实尝试发信、文件路径和访问权限") from None
    finally:
        if conn is not None:
            conn.close()


def _main():
    import argparse

    parser = argparse.ArgumentParser(description="只读查询邮件发送记录（不会加载 .env 或连接 SMTP）")
    parser.add_argument("--db", default=None, help="SQLite 路径，默认 data/email_delivery.sqlite3")
    parser.add_argument("--limit", type=int, default=20)
    parser.add_argument("--recipient", help="按完整收件邮箱筛选")
    parser.add_argument("--status", choices=["sending", "sent", "partial", "not_sent", "unknown"])
    args = parser.parse_args()
    try:
        records = list_email_records(record_db=args.db, limit=args.limit,
                                     recipient=args.recipient, status=args.status)
    except (EmailSendError, ValueError) as error:
        parser.exit(1, str(error) + "\n")
    print(json.dumps(records, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    _main()

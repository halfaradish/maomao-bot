"""邮件投递的持久化/限流/保守重试测试：只使用临时 SQLite 和模拟 SMTP。"""

import asyncio
import json
import os
from pathlib import Path
import smtplib
import sqlite3
import subprocess
import sys
import tempfile
import threading
import unittest
from contextlib import closing
from dataclasses import replace
from unittest.mock import MagicMock, patch

from src.common import email_delivery as delivery
from src.common import email_sender as mail


class EmailDeliveryTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.db = str(Path(self.temp.name) / "email.sqlite3")
        self.environment = patch.dict(os.environ, {
            "EMAIL_RECORD_DB": self.db,
            "EMAIL_WORKERS": "2", "EMAIL_QUEUE_SIZE": "2",
            "EMAIL_RATE_COUNT": "100", "EMAIL_RATE_WINDOW": "60",
            "EMAIL_RECIPIENT_RATE_COUNT": "20", "EMAIL_RECIPIENT_RATE_WINDOW": "3600",
            "EMAIL_RETRY_ATTEMPTS": "1", "EMAIL_RETRY_DELAY": "0",
        })
        self.environment.start()
        self.addCleanup(self.environment.stop)
        self.previous_runtime = delivery._runtime
        delivery._runtime = None
        self.addCleanup(self.shutdown)
        self.config = mail.SMTPConfig(enabled=True, username="sender@example.com",
                                      password="private-auth-code", host="smtp.example.com")
        self.smtp = MagicMock()
        self.smtp.send_message.return_value = {}
        smtp_patch = patch.object(mail.smtplib, "SMTP_SSL", return_value=self.smtp)
        self.factory = smtp_patch.start()
        self.addCleanup(smtp_patch.stop)

    def shutdown(self):
        if delivery._runtime:
            delivery._runtime.executor.shutdown(wait=True)
        delivery._runtime = self.previous_runtime

    async def send(self, **changes):
        args = dict(to="student@example.com", subject="私密主题", text="private-body",
                    config=self.config, idempotency_key="private-request-flag")
        args.update(changes)
        return await mail.send_email(**args)

    def rows(self, table="email_deliveries"):
        with closing(sqlite3.connect(self.db)) as conn:
            conn.row_factory = sqlite3.Row
            return [dict(row) for row in conn.execute("SELECT * FROM " + table)]

    async def test_journal_and_dedupe_survive_new_process(self):
        result = await self.send()
        self.assertTrue(result.record_id)
        self.assertEqual((await self.send()).status, "duplicate")
        script = """
import asyncio, sys
from unittest.mock import patch
from src.common.email_sender import SMTPConfig, send_email
async def main():
    with patch('smtplib.SMTP_SSL', side_effect=AssertionError('must not connect')):
        result = await send_email(to='student@example.com', subject='x', text='x',
            config=SMTPConfig(enabled=True, username='sender@example.com', password='fake'),
            idempotency_key='private-request-flag')
        print(result.status)
asyncio.run(main())
"""
        completed = await asyncio.to_thread(subprocess.run, [sys.executable, "-c", script],
                                            capture_output=True, text=True, timeout=10)
        self.assertEqual(completed.returncode, 0, completed.stderr)
        self.assertEqual(completed.stdout.strip(), "duplicate")
        self.smtp.send_message.assert_called_once()
        row = self.rows()[0]
        self.assertEqual(row["status"], "sent")
        self.assertEqual(row["attempts"], 1)
        self.assertEqual(json.loads(row["recipients"]), ["student@example.com"])
        raw = Path(self.db).read_bytes()
        for private in (b"private-auth-code", b"private-body", b"private-request-flag"):
            self.assertNotIn(private, raw)

    async def test_known_auth_failure_can_be_called_again_with_same_key(self):
        self.smtp.login.side_effect = smtplib.SMTPAuthenticationError(535, b"private-auth-code")
        with self.assertRaises(mail.EmailSendError) as caught:
            await self.send()
        self.assertEqual(caught.exception.delivery_state, "not_sent")
        self.assertEqual(self.rows()[0]["status"], "not_sent")
        self.smtp.login.side_effect = None
        self.assertEqual((await self.send()).status, "sent")
        self.assertEqual(self.rows()[0]["attempts"], 2)
        self.smtp.send_message.assert_called_once()

    async def test_bad_configuration_does_not_poison_key(self):
        with self.assertRaises(mail.EmailConfigurationError):
            await self.send(config=replace(self.config, password=""))
        self.assertFalse(Path(self.db).exists())
        self.assertEqual((await self.send()).status, "sent")

    async def test_transient_pre_submission_error_retries_and_records_each_attempt(self):
        self.smtp.login.side_effect = [OSError("private-network-error"), None]
        with patch.dict(os.environ, {"EMAIL_RETRY_ATTEMPTS": "3"}):
            result = await self.send()
        self.assertEqual(result.status, "sent")
        attempts = self.rows("email_attempts")
        self.assertEqual([row["status"] for row in attempts], ["not_sent", "sent"])
        self.assertEqual(self.smtp.login.call_count, 2)
        self.smtp.send_message.assert_called_once()

    async def test_unknown_submission_is_never_retried_even_after_repeat_call(self):
        self.smtp.send_message.side_effect = TimeoutError("secret-network-detail")
        with patch.dict(os.environ, {"EMAIL_RETRY_ATTEMPTS": "3"}):
            with self.assertRaises(mail.EmailSendError) as first:
                await self.send()
            self.assertEqual(first.exception.delivery_state, "unknown")
            with self.assertRaises(mail.EmailSendError) as second:
                await self.send()
        self.assertEqual(second.exception.code, "uncertain")
        self.assertEqual(second.exception.record_id, first.exception.record_id)
        self.assertEqual(self.rows()[0]["status"], "unknown")
        self.smtp.send_message.assert_called_once()

    async def test_partial_result_is_recorded_and_not_resent(self):
        self.smtp.send_message.return_value = {"bad@example.com": (550, b"private-reason")}
        result = await self.send(to=["student@example.com", "bad@example.com"])
        self.assertEqual(result.status, "partial")
        self.assertEqual(json.loads(self.rows()[0]["refused_codes"]), [["bad@example.com", 550]])
        self.assertEqual((await self.send(to=["student@example.com", "bad@example.com"])).status,
                         "duplicate")
        self.smtp.send_message.assert_called_once()

    async def test_recipient_rate_limit_applies_across_different_requests(self):
        with patch.dict(os.environ, {"EMAIL_RECIPIENT_RATE_COUNT": "1"}):
            await self.send(idempotency_key="first")
            with self.assertRaises(mail.EmailSendError) as caught:
                await self.send(idempotency_key="second")
        self.assertEqual(caught.exception.code, "rate_limited")
        self.assertEqual(caught.exception.delivery_state, "not_sent")
        self.smtp.send_message.assert_called_once()
        self.assertEqual(self.rows()[1]["status"], "not_sent")

    async def test_global_limit_is_atomic_for_concurrent_distinct_recipients(self):
        with patch.dict(os.environ, {"EMAIL_RATE_COUNT": "1"}):
            results = await asyncio.gather(
                self.send(to="one@example.com", idempotency_key="first"),
                self.send(to="two@example.com", idempotency_key="second"),
                return_exceptions=True,
            )
        self.assertEqual(sum(isinstance(result, mail.EmailSendResult) for result in results), 1)
        errors = [result for result in results if isinstance(result, mail.EmailSendError)]
        self.assertEqual(errors[0].code, "rate_limited")
        self.smtp.send_message.assert_called_once()

    async def test_business_quota_can_group_different_recipient_addresses(self):
        with patch.dict(os.environ, {"EMAIL_RECIPIENT_RATE_COUNT": "1"}):
            await self.send(rate_limit_key="one-user", to="one@example.com")
            with self.assertRaises(mail.EmailSendError) as caught:
                await self.send(rate_limit_key="one-user", to="two@example.com", idempotency_key="2")
        self.assertEqual(caught.exception.code, "rate_limited")

    async def test_new_window_allows_limited_request_to_be_called_again(self):
        with patch.dict(os.environ, {"EMAIL_RECIPIENT_RATE_COUNT": "1"}):
            await self.send(idempotency_key="first")
            with self.assertRaises(mail.EmailSendError):
                await self.send(idempotency_key="second")
            with closing(sqlite3.connect(self.db)) as conn, conn:
                conn.execute("UPDATE email_rate_events SET created_at=0")
            self.assertEqual((await self.send(idempotency_key="second")).status, "sent")

    async def test_short_window_process_does_not_erase_long_window_quota(self):
        store = delivery.DeliveryStore(self.db)
        long_window = replace(delivery.DeliveryConfig(), recipient_count=1, recipient_window=86400)
        with patch.object(delivery.time, "time", return_value=100000):
            store.claim("first", ("student@example.com",))
            store.begin_attempt("first", ("same-recipient",), long_window)
        with patch.object(delivery.time, "time", return_value=104000):
            store.claim("other", ("other@example.com",))
            store.begin_attempt("other", ("other-recipient",), delivery.DeliveryConfig())
            store.claim("second", ("student@example.com",))
            with self.assertRaises(delivery._RateLimited):
                store.begin_attempt("second", ("same-recipient",), long_window)

    async def test_queued_arguments_are_snapshotted_before_caller_mutates_lists(self):
        entered, release = threading.Event(), threading.Event()

        def block(*args, **kwargs):
            entered.set()
            release.wait(5)
            return {}

        self.smtp.send_message.side_effect = block
        recipients = ["original@example.com"]
        attachments = []
        with patch.dict(os.environ, {"EMAIL_WORKERS": "1", "EMAIL_QUEUE_SIZE": "1"}):
            first = asyncio.create_task(self.send(idempotency_key="first"))
            second = None
            try:
                self.assertTrue(await asyncio.to_thread(entered.wait, 3))
                second = asyncio.create_task(self.send(to=recipients, attachments=attachments,
                                                        idempotency_key="second"))
                await asyncio.sleep(0)  # 让第二个调用完成参数快照并进入队列。
                recipients[0] = "mutated@example.com"
                attachments.append(mail.EmailAttachment("unexpected.txt", b"unexpected"))
            finally:
                release.set()
                await first
                if second:
                    await second
        last_call = self.smtp.send_message.call_args
        self.assertEqual(last_call.kwargs["to_addrs"], ["original@example.com"])
        self.assertEqual(list(last_call.args[0].iter_attachments()), [])

    async def test_concurrent_duplicate_is_reserved_before_smtp_finishes(self):
        entered, release = threading.Event(), threading.Event()

        def block(*args, **kwargs):
            entered.set()
            release.wait(5)
            return {}

        self.smtp.send_message.side_effect = block
        task = asyncio.create_task(self.send())
        try:
            self.assertTrue(await asyncio.to_thread(entered.wait, 3))
            with self.assertRaises(mail.EmailSendError) as caught:
                await self.send()
            self.assertEqual(caught.exception.code, "in_progress")
        finally:
            release.set()
            await task
        self.smtp.send_message.assert_called_once()

    async def test_cancelled_caller_does_not_free_slot_or_lose_smtp_outcome(self):
        entered, release = threading.Event(), threading.Event()

        def block(*args, **kwargs):
            entered.set()
            release.wait(5)
            return {}

        self.smtp.send_message.side_effect = block
        with patch.dict(os.environ, {"EMAIL_WORKERS": "1", "EMAIL_QUEUE_SIZE": "0"}):
            task = asyncio.create_task(self.send())
            try:
                self.assertTrue(await asyncio.to_thread(entered.wait, 3))
                task.cancel()
                with self.assertRaises(asyncio.CancelledError):
                    await task
                with self.assertRaises(mail.EmailSendError) as caught:
                    await self.send(idempotency_key="second")
                self.assertEqual(caught.exception.code, "busy")
            finally:
                release.set()
                await asyncio.to_thread(delivery._runtime.executor.shutdown, wait=True)
        self.assertEqual(self.rows()[0]["status"], "sent")
        self.smtp.send_message.assert_called_once()

    async def test_dry_run_and_disabled_do_not_reserve_or_create_records(self):
        self.assertEqual((await self.send(config=mail.SMTPConfig())).status, "disabled")
        self.assertEqual((await self.send(config=replace(self.config, dry_run=True))).status, "dry_run")
        self.assertFalse(Path(self.db).exists())
        self.factory.assert_not_called()

    async def test_storage_failure_before_smtp_fails_closed(self):
        with patch.object(delivery, "DeliveryStore", side_effect=sqlite3.OperationalError("private-path")):
            with self.assertRaises(mail.EmailSendError) as caught:
                await self.send()
        self.assertEqual(caught.exception.code, "storage")
        self.assertEqual(caught.exception.delivery_state, "not_sent")
        self.assertNotIn("private-path", str(caught.exception))
        self.factory.assert_not_called()

    async def test_storage_failure_after_acceptance_is_unknown_and_not_resent(self):
        with patch.object(delivery.DeliveryStore, "finish", side_effect=sqlite3.OperationalError("disk")):
            with self.assertRaises(mail.EmailSendError) as caught:
                await self.send()
        self.assertEqual(caught.exception.delivery_state, "unknown")
        with self.assertRaises(mail.EmailSendError) as repeated:
            await self.send()
        self.assertEqual(repeated.exception.code, "in_progress")
        self.smtp.send_message.assert_called_once()

    async def test_key_cannot_be_reused_for_different_recipients(self):
        await self.send()
        with self.assertRaises(mail.EmailSendError) as caught:
            await self.send(to="someone-else@example.com")
        self.assertEqual(caught.exception.code, "key_conflict")

    async def test_read_only_query_filters_and_never_creates_missing_db(self):
        missing = str(Path(self.temp.name) / "missing.sqlite3")
        with self.assertRaises(mail.EmailSendError):
            delivery.list_email_records(record_db=missing)
        self.assertFalse(Path(missing).exists())
        await self.send()
        self.assertEqual(len(delivery.list_email_records(recipient="student@example.com", status="sent")), 1)
        self.assertEqual(delivery.list_email_records(recipient="other@example.com"), [])
        with patch.object(Path, "expanduser", return_value=Path(self.db)) as expanded:
            self.assertEqual(len(delivery.list_email_records(record_db="~/email.sqlite3")), 1)
            expanded.assert_called_once()


class DeliveryConfigTests(unittest.TestCase):
    def test_invalid_limits_fail_without_initializing_services(self):
        for name, value in [("EMAIL_WORKERS", "0"), ("EMAIL_QUEUE_SIZE", "-1"),
                            ("EMAIL_RETRY_ATTEMPTS", "6"), ("EMAIL_RETRY_DELAY", "nan"),
                            ("EMAIL_RATE_WINDOW", "inf"), ("EMAIL_RECORD_DB", ":memory:")]:
            with self.subTest(name=name), patch.dict(os.environ, {name: value}):
                with self.assertRaises(mail.EmailConfigurationError):
                    delivery.DeliveryConfig.from_env()


if __name__ == "__main__":
    unittest.main()

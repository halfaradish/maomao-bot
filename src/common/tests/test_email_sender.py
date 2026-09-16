"""公共邮件工具的离线回归测试；不会加载 Bot、读取真实 .env 或连接 SMTP。"""

import asyncio
import importlib.util
import smtplib
import ssl
import sys
import threading
import types
import unittest
from dataclasses import replace
from email import policy
from email.parser import BytesParser
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch


# 直接加载传输模块，隔离测试中的模块替换及外部服务。
spec = importlib.util.spec_from_file_location(
    "_test_transport.email_sender", Path(__file__).resolve().parents[1] / "email_sender.py"
)
mail = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = mail
spec.loader.exec_module(mail)


class EmailSenderTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.config = mail.SMTPConfig(
            enabled=True, username="sender@example.com", password="test-secret-only",
            from_name="邮件测试", host="smtp.example.com",
        )
        self.smtp = MagicMock()
        self.smtp.send_message.return_value = {}
        self.ssl_patch = patch.object(mail.smtplib, "SMTP_SSL", return_value=self.smtp)
        self.smtp_patch = patch.object(mail.smtplib, "SMTP", return_value=self.smtp)
        self.ssl_factory = self.ssl_patch.start()
        self.smtp_factory = self.smtp_patch.start()
        self.addCleanup(self.ssl_patch.stop)
        self.addCleanup(self.smtp_patch.stop)
        # 单测只检验邮件构造/传输；生产调度器的记录、重试、限流由独立测试覆盖。
        async def direct_dispatch(*, config, message_args, **kwargs):
            return await asyncio.to_thread(mail._send_sync, config, **message_args)

        self.dispatch = AsyncMock(side_effect=direct_dispatch)
        package = types.ModuleType("_test_transport")
        package.__path__ = []
        dispatcher = types.ModuleType("_test_transport.email_delivery")
        dispatcher.dispatch_email = self.dispatch
        self.module_patch = patch.dict(sys.modules, {
            "_test_transport": package, "_test_transport.email_delivery": dispatcher,
        })
        self.module_patch.start()
        self.addCleanup(self.module_patch.stop)

    async def send(self, **kwargs):
        args = dict(to="recipient@example.com", subject="入群结果", text="你好，审核未通过。", config=self.config)
        args.update(kwargs)
        return await mail.send_email(**args)

    async def test_text_mime_tls_and_acceptance(self):
        result = await self.send()
        self.assertEqual(result.status, "sent")
        self.assertEqual(result.accepted, ("recipient@example.com",))
        message = self.smtp.send_message.call_args.args[0]
        self.assertEqual(message.get_content_type(), "text/plain")
        self.assertIn("审核未通过", message.get_content())
        self.assertTrue(message.as_bytes().isascii())
        self.assertEqual(str(message["Subject"]), "入群结果")
        self.assertTrue(message["Date"])
        self.assertEqual(message["Message-ID"], result.message_id)
        context = self.ssl_factory.call_args.kwargs["context"]
        self.assertTrue(context.check_hostname)
        self.assertEqual(context.verify_mode, ssl.CERT_REQUIRED)
        self.smtp.login.assert_called_once_with("sender@example.com", "test-secret-only")
        self.smtp.close.assert_called_once()
        self.smtp_factory.assert_not_called()

    async def test_html_alternative_attachment_and_bcc_envelope(self):
        await self.send(
            to=["recipient@example.com", "recipient@example.com"],
            cc="copy@example.com", bcc=["hidden@example.com", "copy@example.com"],
            html="<h1>你好</h1><p>审核未通过</p>", reply_to="support@example.com",
            attachments=[mail.EmailAttachment("说明.txt", "邮件说明".encode(), "text/plain")],
        )
        call = self.smtp.send_message.call_args
        self.assertEqual(call.kwargs["to_addrs"], ["recipient@example.com", "copy@example.com", "hidden@example.com"])
        raw = call.args[0].as_bytes()
        self.assertTrue(raw.isascii())
        self.assertNotIn(b"hidden@example.com", raw)
        message = BytesParser(policy=policy.default).parsebytes(raw)
        self.assertIsNone(message["Bcc"])
        self.assertEqual(str(message["Reply-To"]), "support@example.com")
        self.assertEqual(message.get_content_type(), "multipart/mixed")
        self.assertEqual(message.get_payload(0).get_content_type(), "multipart/alternative")
        self.assertIn("你好", message.get_body(preferencelist=("html",)).get_content())
        self.assertIn("你好", message.get_body(preferencelist=("plain",)).get_content())
        attachment = next(message.iter_attachments())
        self.assertEqual(attachment.get_filename(), "说明.txt")
        self.assertEqual(attachment.get_payload(decode=True), "邮件说明".encode())

    async def test_html_only_and_bcc_only(self):
        result = await self.send(to=(), bcc="hidden@example.com", text=None, html="<p>你好</p>")
        message = self.smtp.send_message.call_args.args[0]
        self.assertEqual(message.get_content_type(), "text/html")
        self.assertTrue(message.as_bytes().isascii())
        self.assertEqual(result.accepted, ("hidden@example.com",))
        self.assertIsNone(message["To"])
        self.assertIsNone(message["Bcc"])

    async def test_starttls_happens_before_login(self):
        await self.send(config=replace(self.config, security="starttls", port=587))
        calls = [call[0] for call in self.smtp.mock_calls]
        self.assertEqual(calls[:4], ["ehlo", "starttls", "ehlo", "login"])
        self.ssl_factory.assert_not_called()
        self.assertEqual(self.smtp_factory.call_args.args, ("smtp.example.com", 587))

    async def test_starttls_unavailable_never_logs_in(self):
        self.smtp.starttls.side_effect = smtplib.SMTPNotSupportedError("private SMTP response")
        with self.assertRaises(mail.EmailSendError) as error:
            await self.send(config=replace(self.config, security="starttls", port=587))
        self.assertEqual(error.exception.code, "tls")
        self.assertNotIn("private", str(error.exception))
        self.smtp.login.assert_not_called()
        self.smtp.send_message.assert_not_called()

    async def test_partial_refusal_is_not_reported_as_complete_success(self):
        self.smtp.send_message.return_value = {"bad@example.com": (550, b"no mailbox")}
        result = await self.send(to=["good@example.com", "bad@example.com"])
        self.assertEqual(result.status, "partial")
        self.assertEqual(result.accepted, ("good@example.com",))
        self.assertEqual(result.refused, ("bad@example.com",))
        self.assertEqual(result.refused_codes, (("bad@example.com", 550),))
        self.assertNotIn("no mailbox", repr(result))
        self.smtp.send_message.assert_called_once()

    async def test_all_refused_is_sanitized_error(self):
        self.smtp.send_message.side_effect = smtplib.SMTPRecipientsRefused({"recipient@example.com": (550, b"private")})
        with self.assertRaises(mail.EmailSendError) as error:
            await self.send()
        self.assertEqual(error.exception.code, "recipients_refused")
        self.assertEqual(error.exception.delivery_state, "not_sent")
        self.assertEqual(error.exception.smtp_code, 550)
        self.assertFalse(error.exception.retryable)
        self.assertNotIn("recipient@example.com", str(error.exception))
        self.smtp.send_message.assert_called_once()

    async def test_disabled_and_dry_run_do_not_connect(self):
        disabled = await self.send(config=mail.SMTPConfig())
        self.assertEqual(disabled.status, "disabled")
        dry_run = await self.send(config=replace(self.config, dry_run=True, password=""))
        self.assertEqual(dry_run.status, "dry_run")
        self.assertEqual(dry_run.accepted, ())
        self.assertTrue(dry_run.message_id)
        self.ssl_factory.assert_not_called()
        self.smtp_factory.assert_not_called()

    async def test_invalid_inputs_fail_before_network(self):
        cases = [
            {"subject": "hello\r\nBcc: victim@example.com"},
            {"to": "a@example.com\nBcc: victim@example.com"},
            {"to": "a@example.com,b@example.com"},
            {"to": "not-an-address"},
            {"to": ()},
            {"text": None, "html": None},
            {"reply_to": "invalid"},
            {"config": replace(self.config, password="")},
            {"config": replace(self.config, security="none")},
            {"config": replace(self.config, port=0)},
            {"config": replace(self.config, timeout=float("nan"))},
            {"config": replace(self.config, from_name="name\r\nBcc: x@example.com")},
            {"attachments": [mail.EmailAttachment("../secret.txt", b"foo")]},
            {"attachments": [mail.EmailAttachment("x.txt", b"foo", "text/plain; charset=UTF-8")]},
            {"config": replace(self.config, max_message_bytes=100)},
            {"attachments": [mail.EmailAttachment("big.txt", b"x" * 2048)], "config": replace(self.config, max_message_bytes=1024)},
        ]
        for kwargs in cases:
            with self.subTest(kwargs=list(kwargs)):
                with self.assertRaises(mail.EmailSendError):
                    await self.send(**kwargs)
        self.ssl_factory.assert_not_called()
        self.smtp_factory.assert_not_called()

    async def test_errors_never_expose_credentials_or_retry(self):
        cases = [
            (smtplib.SMTPAuthenticationError(535, b"test-secret-only"), "authentication"),
            (TimeoutError("test-secret-only"), "timeout"),
            (smtplib.SMTPServerDisconnected("test-secret-only"), "connection"),
            (smtplib.SMTPDataError(554, b"test-secret-only"), "smtp"),
            (OSError("test-secret-only"), "connection"),
        ]
        for exc, code in cases:
            with self.subTest(code=code):
                self.smtp.reset_mock()
                self.smtp.login.side_effect = exc
                with self.assertRaises(mail.EmailSendError) as error:
                    await self.send()
                self.assertEqual(error.exception.code, code)
                self.assertNotIn("test-secret-only", str(error.exception))
                self.smtp.login.assert_called_once()
                self.smtp.close.assert_called_once()
        self.assertNotIn("test-secret-only", repr(self.config))

    async def test_failures_before_submission_are_safe_to_classify(self):
        cases = [
            (TimeoutError("private"), "timeout", True, None),
            (OSError("private"), "connection", True, None),
            (smtplib.SMTPServerDisconnected("private"), "connection", True, None),
            (smtplib.SMTPConnectError(421, b"private"), "smtp", True, 421),
            (smtplib.SMTPConnectError(554, b"private"), "smtp", False, 554),
            (ssl.SSLCertVerificationError("private"), "tls", False, None),
            (RuntimeError("private"), "internal", False, None),
        ]
        for exc, code, retryable, smtp_code in cases:
            with self.subTest(code=code, smtp_code=smtp_code):
                self.ssl_factory.side_effect = exc
                with self.assertRaises(mail.EmailSendError) as result:
                    await self.send()
                error = result.exception
                self.assertEqual(error.code, code)
                self.assertEqual(error.delivery_state, "not_sent")
                self.assertEqual(error.retryable, retryable)
                self.assertEqual(error.smtp_code, smtp_code)
                self.assertTrue(error.message_id)
                self.assertNotIn("private", str(error))
        self.smtp.send_message.assert_not_called()

    async def test_authentication_even_transient_is_not_retried(self):
        self.smtp.login.side_effect = smtplib.SMTPAuthenticationError(454, b"private")
        with self.assertRaises(mail.EmailSendError) as result:
            await self.send()
        self.assertEqual(result.exception.delivery_state, "not_sent")
        self.assertFalse(result.exception.retryable)
        self.assertEqual(result.exception.smtp_code, 454)
        self.smtp.send_message.assert_not_called()

    async def test_disconnect_or_unexpected_error_during_submission_is_unknown(self):
        for exc in [
            TimeoutError("private"), OSError("private"),
            smtplib.SMTPServerDisconnected("private"), ssl.SSLError("private"),
            RuntimeError("private"), smtplib.SMTPException("private"),
            smtplib.SMTPResponseException(421, b"private"),
        ]:
            with self.subTest(error=type(exc).__name__):
                self.smtp.send_message.side_effect = exc
                with self.assertRaises(mail.EmailSendError) as result:
                    await self.send()
                self.assertEqual(result.exception.delivery_state, "unknown")
                self.assertFalse(result.exception.retryable)
                self.assertNotIn("private", str(result.exception))

    async def test_explicit_mail_and_data_refusals_are_not_sent(self):
        for code in [451, 554]:
            for exc in [smtplib.SMTPDataError(code, b"private"),
                        smtplib.SMTPSenderRefused(code, b"private", "sender@example.com")]:
                with self.subTest(code=code, error=type(exc).__name__):
                    self.smtp.send_message.side_effect = exc
                    with self.assertRaises(mail.EmailSendError) as result:
                        await self.send()
                    self.assertEqual(result.exception.delivery_state, "not_sent")
                    self.assertEqual(result.exception.retryable, code == 451)
                    self.assertEqual(result.exception.smtp_code, code)

    async def test_recipient_retry_requires_all_refusals_to_be_transient(self):
        for second_code, retryable in [(451, True), (550, False)]:
            self.smtp.send_message.side_effect = smtplib.SMTPRecipientsRefused({
                "first@example.com": (450, b"private"),
                "second@example.com": (second_code, b"private"),
            })
            with self.assertRaises(mail.EmailSendError) as result:
                await self.send(to=["first@example.com", "second@example.com"])
            self.assertEqual(result.exception.delivery_state, "not_sent")
            self.assertEqual(result.exception.retryable, retryable)
            self.assertIsNone(result.exception.smtp_code)

    async def test_invalid_message_type_is_definitely_not_sent(self):
        with self.assertRaises(mail.EmailSendError) as result:
            await self.send(text=object())
        self.assertEqual(result.exception.code, "message")
        self.assertEqual(result.exception.delivery_state, "not_sent")
        self.assertFalse(result.exception.retryable)
        self.ssl_factory.assert_not_called()

    async def test_inline_images_and_regular_attachments_keep_mime_tree(self):
        for plain_text in [None, "纯文字版本"]:
            with self.subTest(text=plain_text):
                await self.send(
                    text=plain_text, html='<p>图片</p><img src="cid:logo"><img src="cid:footer">',
                    attachments=[
                        mail.EmailAttachment("guide.pdf", b"pdf", "application/pdf"),
                        mail.EmailAttachment("logo.png", b"png", "image/png", content_id="logo"),
                        mail.EmailAttachment("footer.jpg", b"jpg", "image/jpeg", content_id="footer"),
                    ],
                )
                message = self.smtp.send_message.call_args.args[0]
                self.assertEqual(message.get_content_type(), "multipart/mixed")
                html_part = message.get_body(preferencelist=("html",))
                self.assertIn("cid:logo", html_part.get_content())
                related = next(part for part in message.walk() if part.get_content_type() == "multipart/related")
                self.assertEqual(related.get_payload(0).get_content_type(), "text/html")
                images = list(related.iter_attachments())
                self.assertEqual([part["Content-ID"] for part in images], ["<logo>", "<footer>"])
                self.assertTrue(all(part.get_content_disposition() == "inline" for part in images))
                self.assertEqual([part.get_filename() for part in message.iter_attachments()], ["guide.pdf"])
                self.assertTrue(message.as_bytes().isascii())

    async def test_inline_image_validation(self):
        valid = mail.EmailAttachment("logo.png", b"png", "image/png", content_id="logo")
        for kwargs in [
            {"attachments": [valid]},
            {"html": "<p>html</p>", "attachments": [replace(valid, content_id="<unsafe>")]},
            {"html": "<p>html</p>", "attachments": [replace(valid, content_id="logo\r\nBcc: bad")]},
            {"html": "<p>html</p>", "attachments": [replace(valid, content_type="text/plain")]},
            {"html": "<p>html</p>", "attachments": [valid, valid]},
        ]:
            with self.subTest(args=list(kwargs)):
                with self.assertRaises(mail.EmailSendError) as result:
                    await self.send(**kwargs)
                self.assertEqual(result.exception.delivery_state, "not_sent")
        self.ssl_factory.assert_not_called()

    async def test_public_api_forwards_delivery_keys(self):
        await self.send(idempotency_key="join-request:123", rate_limit_key="qq:123")
        args = self.dispatch.call_args.kwargs
        self.assertEqual(args["idempotency_key"], "join-request:123")
        self.assertEqual(args["rate_limit_key"], "qq:123")
        self.assertIs(args["config"], self.config)
        self.assertEqual(args["message_args"]["to"], "recipient@example.com")

    async def test_unexpected_dispatch_failure_is_conservatively_unknown(self):
        self.dispatch.side_effect = RuntimeError("private")
        with self.assertRaises(mail.EmailSendError) as result:
            await self.send()
        self.assertEqual(result.exception.delivery_state, "unknown")
        self.assertFalse(result.exception.retryable)
        self.assertNotIn("private", str(result.exception))

    async def test_disconnect_during_quit_keeps_accepted_result(self):
        self.smtp.quit.side_effect = smtplib.SMTPServerDisconnected("bye")
        result = await self.send()
        self.assertEqual(result.status, "sent")
        self.smtp.send_message.assert_called_once()
        self.smtp.close.assert_called_once()

    async def test_close_error_does_not_mask_accepted_result(self):
        self.smtp.close.side_effect = OSError("already closed")
        self.assertEqual((await self.send()).status, "sent")

    async def test_smtp_work_runs_off_event_loop(self):
        loop_thread = threading.get_ident()
        entered = threading.Event()
        release = threading.Event()
        worker_threads = []

        def block_send(*args, **kwargs):
            worker_threads.append(threading.get_ident())
            entered.set()
            release.wait(timeout=2)
            return {}

        self.smtp.send_message.side_effect = block_send
        task = asyncio.create_task(self.send())
        try:
            self.assertTrue(await asyncio.to_thread(entered.wait, 2))
            self.assertFalse(task.done())
            self.assertNotEqual(worker_threads[0], loop_thread)
        finally:
            release.set()
            await task


class SMTPConfigTests(unittest.TestCase):
    def test_env_defaults_and_explicit_values(self):
        config = mail.SMTPConfig.from_env({"EMAIL_ENABLED": "true", "EMAIL_DRY_RUN": "1", "SMTP_SECURITY": "starttls"})
        self.assertTrue(config.enabled)
        self.assertTrue(config.dry_run)
        self.assertEqual(config.port, 587)
        self.assertEqual(mail.SMTPConfig.from_env({"EMAIL_ENABLED": "false", "SMTP_PORT": "bad"}).enabled, False)
        self.assertEqual(mail.SMTPConfig.from_env({}).enabled, False)

    def test_invalid_environment_values(self):
        for env in [
            {"EMAIL_ENABLED": "maybe"},
            {"EMAIL_ENABLED": "true", "EMAIL_DRY_RUN": "maybe"},
            {"EMAIL_ENABLED": "true", "SMTP_PORT": "test-secret-only"},
        ]:
            with self.subTest(keys=list(env)):
                with self.assertRaises(mail.EmailConfigurationError) as error:
                    mail.SMTPConfig.from_env(env)
                self.assertNotIn("test-secret-only", str(error.exception))


if __name__ == "__main__":
    unittest.main()

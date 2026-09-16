"""邮件接入测试：隔离 NoneBot/数据库/SMTP，不实际发信。"""

import asyncio
import importlib.util
from pathlib import Path
import sys
import tempfile
import types
import unittest
from unittest.mock import AsyncMock, Mock, patch


PLUGIN = Path(__file__).resolve().parents[2] / "plugins/group_sentinel"
PACKAGE = "src.plugins.group_sentinel"


class FakeEmailSendError(Exception):
    def __init__(self, code, message, *, delivery_state="not_sent", retryable=False):
        super().__init__(message)
        self.code = code
        self.delivery_state = delivery_state
        self.retryable = retryable


def module(name, **attributes):
    result = types.ModuleType(name)
    result.__dict__.update(attributes)
    return result


class PendingReviewEmailTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.sender = AsyncMock(return_value=types.SimpleNamespace(status="sent"))
        self.logger = Mock()
        self.audit = AsyncMock(return_value=(False, "专业编码不存在"))
        self.group_enabled = AsyncMock(return_value=True)
        self.handlers = []

        def register_handler():
            def decorate(handler):
                self.handlers.append(handler)
                return handler
            return decorate

        self.fake_nonebot = module(
            "nonebot",
            logger=self.logger,
            on_request=Mock(return_value=types.SimpleNamespace(handle=register_handler)),
            get_driver=lambda: types.SimpleNamespace(on_startup=lambda fn: fn),
        )
        stubs = {
            "src": module("src", __path__=[]),
            "src.plugins": module("src.plugins", __path__=[]),
            "src.common": module("src.common", __path__=[str(PLUGIN.parents[1] / "common")]),
            PACKAGE: module(PACKAGE, __path__=[str(PLUGIN)]),
            "nonebot": self.fake_nonebot,
            "nonebot.plugin": module("nonebot.plugin", PluginMetadata=lambda **kw: kw),
            "nonebot.rule": module("nonebot.rule", Rule=lambda fn: fn),
            "nonebot.adapters": module("nonebot.adapters", __path__=[]),
            "nonebot.adapters.onebot": module("nonebot.adapters.onebot", __path__=[]),
            "nonebot.adapters.onebot.v11": module(
                "nonebot.adapters.onebot.v11", Bot=object, GroupRequestEvent=object
            ),
            "sqlalchemy": module("sqlalchemy", select=Mock()),
            "src.common.email_sender": module(
                "src.common.email_sender",
                send_email=self.sender,
                EmailSendError=FakeEmailSendError,
            ),
            "src.common.plugin_meta": module(
                "src.common.plugin_meta",
                PluginGroupEnum=types.SimpleNamespace(
                    GROUP_MANAGE=types.SimpleNamespace(value="group_manage")
                ),
                PluginBadgeColor=types.SimpleNamespace(
                    YELLOW=types.SimpleNamespace(value="yellow"),
                    GREEN=types.SimpleNamespace(value="green"),
                ),
            ),
            "src.common.database": module(
                "src.common.database", async_session_factory=Mock()
            ),
            "src.common.permission": module("src.common.permission", __path__=[]),
            "src.common.permission.models": module(
                "src.common.permission.models", PermissionGroup=Mock(), PermissionGroupPerm=Mock()
            ),
            f"{PACKAGE}.permissions": module(f"{PACKAGE}.permissions"),
            f"{PACKAGE}.auditor": module(
                f"{PACKAGE}.auditor", audit_join_request=self.audit
            ),
            "src.plugins.auto_manage_group": module(
                "src.plugins.auto_manage_group", __path__=[]
            ),
            "src.plugins.auto_manage_group.group_checker": module(
                "src.plugins.auto_manage_group.group_checker",
                is_group_feature_enabled=self.group_enabled,
            ),
        }
        self.modules_patch = patch.dict(sys.modules, stubs)
        self.modules_patch.start()
        self.addCleanup(self.modules_patch.stop)
        self.env_patch = patch.dict("os.environ", {"GROUP_SENTINEL_ENABLED": "true"})
        self.env_patch.start()
        self.addCleanup(self.env_patch.stop)
        self.config = self.load("config").Config(group_sentinel_email_enabled=True)
        self.fake_nonebot.get_plugin_config = lambda cls: self.config
        self.load("email_templates")
        self.notifier = self.load("notifier")
        self.load("__init__")
        self.handler = self.handlers[0]
        self.bot = types.SimpleNamespace(self_id="123", send_group_msg=AsyncMock())
        self.event = types.SimpleNamespace(
            group_id=456,
            user_id=789,
            comment="private applicant text",
            flag="request-1",
            approve=AsyncMock(),
            reject=AsyncMock(),
        )

    def load(self, name):
        fullname = PACKAGE if name == "__init__" else f"{PACKAGE}.{name}"
        spec = importlib.util.spec_from_file_location(fullname, PLUGIN / f"{name}.py")
        loaded = importlib.util.module_from_spec(spec)
        sys.modules[fullname] = loaded
        spec.loader.exec_module(loaded)
        return loaded

    def notify(self, **changes):
        kwargs = dict(
            bot_id="123", group_id=456, user_id=789, request_flag="request-1",
            reason="专业编码不存在", config=self.config,
        )
        kwargs.update(changes)
        return self.notifier.notify_pending_review(**kwargs)

    async def test_approved_application_never_sends_mail(self):
        self.audit.return_value = (True, "")
        await self.handler(self.bot, self.event)
        self.event.approve.assert_awaited_once_with(self.bot)
        self.event.reject.assert_not_awaited()
        self.sender.assert_not_awaited()

    async def test_group_without_feature_is_not_handled(self):
        self.group_enabled.return_value = False
        await self.handler(self.bot, self.event)
        self.audit.assert_not_awaited()
        self.event.reject.assert_not_awaited()
        self.sender.assert_not_awaited()

    async def test_pending_review_notice_precedes_mail_without_rejecting(self):
        order = []

        async def send(*args, **kwargs):
            order.append("mail")
            return types.SimpleNamespace(status="sent")

        async def group_notice(*args, **kwargs):
            order.append("group")

        self.sender.side_effect = send
        self.bot.send_group_msg.side_effect = group_notice
        await self.handler(self.bot, self.event)
        self.assertEqual(order, ["group", "mail", "group"])
        mail = self.sender.await_args.kwargs
        self.assertEqual(mail["to"], "789@qq.com")
        self.assertIn("456", mail["text"])
        self.assertIn("专业编码不存在", mail["text"])
        self.assertNotIn(self.event.comment, mail["text"])
        self.assertIsNone(mail["html"])
        self.assertEqual(mail["idempotency_key"], "group_sentinel:pending_review:123:456:request-1")
        self.assertEqual(mail["rate_limit_key"], "qq:789")
        notices = self.bot.send_group_msg.await_args_list
        self.assertIn("处理结果稍后通知", notices[0].kwargs["message"])
        self.assertIn("已提交邮件服务器", notices[1].kwargs["message"])
        self.event.reject.assert_not_awaited()
        self.event.approve.assert_not_awaited()
        self.assertEqual(mail["subject"], "入群申请待人工复核")
        self.assertIn("等待管理员人工复核", mail["text"])
        self.assertIn("不是最终拒绝", mail["text"])
        self.assertIn("无需重复提交申请", mail["text"])
        self.assertNotIn("重新申请", mail["text"])
        self.assertIn("挂起待人工审查", notices[0].kwargs["message"])
        self.assertNotIn("拒绝原因", notices[0].kwargs["message"])

    async def test_pending_review_uses_real_public_mailer_with_mock_smtp(self):
        # 接通真实工具与真实通知模块，仅替换最外层 SMTP，检验二者接口及 MIME。
        path = PLUGIN.parents[1] / "common/email_sender.py"
        spec = importlib.util.spec_from_file_location("src.common.email_sender", path)
        mailer = importlib.util.module_from_spec(spec)
        sys.modules[spec.name] = mailer
        spec.loader.exec_module(mailer)
        # 避免别的测试预先导入的调度器继续引用另一个 mailer 模块实例。
        sys.modules.pop("src.common.email_delivery", None)
        smtp = Mock()
        smtp.send_message.return_value = {}
        config = mailer.SMTPConfig(
            enabled=True, host="smtp.example.com", username="sender@example.com",
            password="fake-test-password",
        )
        self.config.group_sentinel_email_html = True
        with tempfile.TemporaryDirectory() as directory, \
             patch.dict("os.environ", {
                 "EMAIL_RECORD_DB": str(Path(directory) / "email-test.sqlite3"),
                 "EMAIL_RETRY_ATTEMPTS": "1",
                 "EMAIL_RECIPIENT_RATE_COUNT": "100",
             }), \
             patch.object(mailer.SMTPConfig, "from_env", return_value=config), \
             patch.object(mailer.smtplib, "SMTP_SSL", return_value=smtp), \
             patch.object(self.notifier, "send_email", mailer.send_email), \
             patch.object(self.notifier, "EmailSendError", mailer.EmailSendError):
            try:
                await self.handler(self.bot, self.event)
                self.assertEqual(await self.notify(), "duplicate")
                smtp.send_message.assert_called_once()
            finally:
                dispatcher = sys.modules.get("src.common.email_delivery")
                if dispatcher is not None and dispatcher._runtime is not None:
                    dispatcher._runtime.executor.shutdown(wait=True)
        call = smtp.send_message.call_args
        self.assertEqual(call.kwargs["to_addrs"], ["789@qq.com"])
        self.assertEqual(call.args[0].get_content_type(), "multipart/alternative")
        self.assertIn("专业编码不存在", call.args[0].get_body(preferencelist=("html",)).get_content())
        self.assertIn("入群申请待人工复核", call.args[0].get_body(preferencelist=("html",)).get_content())
        self.assertIn("无需重复提交申请", call.args[0].get_body(preferencelist=("plain",)).get_content())
        self.assertIn("已提交邮件服务器", self.bot.send_group_msg.await_args.kwargs["message"])

    async def test_pending_review_does_not_call_qq_rejection_api(self):
        self.event.reject.side_effect = AssertionError("must preserve pending request")
        self.event.approve.side_effect = AssertionError("must not approve flagged request")
        await self.handler(self.bot, self.event)
        self.event.reject.assert_not_awaited()
        self.event.approve.assert_not_awaited()
        self.sender.assert_awaited_once()

    async def test_email_failure_preserves_group_notice_and_hides_error_details(self):
        self.sender.side_effect = FakeEmailSendError("smtp_error", "private-secret")
        await self.handler(self.bot, self.event)
        self.assertEqual(self.bot.send_group_msg.await_count, 2)
        self.assertIn("发送失败", self.bot.send_group_msg.await_args.kwargs["message"])
        self.assertNotIn("private-secret", str(self.logger.warning.call_args_list))
        self.event.reject.assert_not_awaited()
        self.event.approve.assert_not_awaited()
        # 明确未发送的错误不再被插件的本地缓存永久拦截，重试交给公共工具。
        self.sender.side_effect = None
        self.assertEqual(await self.notify(), "sent")
        self.assertEqual(self.sender.await_count, 2)

    async def test_unexpected_mail_error_also_preserves_group_notice(self):
        self.sender.side_effect = RuntimeError("private-secret")
        await self.handler(self.bot, self.event)
        self.assertEqual(self.bot.send_group_msg.await_count, 2)
        self.assertIn("状态不确定", self.bot.send_group_msg.await_args.kwargs["message"])
        self.assertNotIn("private-secret", str(self.logger.warning.call_args_list))

    async def test_plugin_mail_disabled_preserves_group_notice(self):
        self.config.group_sentinel_email_enabled = False
        await self.handler(self.bot, self.event)
        self.event.reject.assert_not_awaited()
        self.event.approve.assert_not_awaited()
        self.sender.assert_not_awaited()
        self.bot.send_group_msg.assert_awaited_once()
        self.assertIn("未启用", self.bot.send_group_msg.await_args.kwargs["message"])

    async def test_html_escapes_reason_and_contact_and_includes_plain_text(self):
        self.config.group_sentinel_email_html = True
        self.config.group_sentinel_email_contact = "<script>unsafe</script>"
        await self.notify(reason='<img src="x">& bad')
        mail = self.sender.await_args.kwargs
        self.assertIn('<img src="x">& bad', mail["text"])
        self.assertIn("&lt;img", mail["html"])
        self.assertIn("&lt;script&gt;", mail["html"])
        self.assertNotIn("<img", mail["html"])
        self.assertNotIn("<script>", mail["html"])

    async def test_html_card_has_pending_status_and_no_external_dependencies(self):
        self.config.group_sentinel_email_html = True
        await self.notify()
        mail = self.sender.await_args.kwargs
        self.assertIn('name="viewport"', mail["html"])
        self.assertIn('role="presentation"', mail["html"])
        self.assertIn("max-width:600px", mail["html"])
        self.assertIn("初审标记原因", mail["html"])
        self.assertIn("接下来怎么做", mail["html"])
        self.assertIn("需要补充信息", mail["html"])
        for content in (mail["html"], mail["text"]):
            self.assertIn("不是最终拒绝", content)
            self.assertIn("无需重复提交申请", content)
            self.assertNotIn("重新申请", content)
        for element in ("<script", "<link", "<img", "<iframe", "<form", "http://", "https://"):
            self.assertNotIn(element, mail["html"])

    async def test_html_header_reason_and_next_step_typography(self):
        self.config.group_sentinel_email_html = True
        await self.notify(reason="示例初审原因")
        html = self.sender.await_args.kwargs["html"]
        heading = html.index("<h1")
        badge = html.index(">待人工复核</span>")
        self.assertLess(heading, badge)
        self.assertNotIn("</tr>", html[heading:badge])
        self.assertIn(
            'font-size:18px;line-height:30px;font-weight:700;color:#33364f;">示例初审原因</p>',
            html,
        )
        self.assertEqual(
            html.count("font-size:15px;line-height:27px;font-weight:400;color:#33364f;"),
            2,
        )

    async def test_empty_contact_omits_contact_card_in_both_versions(self):
        self.config.group_sentinel_email_html = True
        self.config.group_sentinel_email_contact = "  "
        await self.notify()
        mail = self.sender.await_args.kwargs
        self.assertNotIn("需要补充信息", mail["html"])
        self.assertNotIn("如需人工复核，可联系", mail["html"])
        self.assertNotIn("如需人工复核，可联系", mail["text"])
        self.assertNotIn("1950482412", mail["html"])

    async def test_multiline_long_reason_is_preserved_and_escaped(self):
        self.config.group_sentinel_email_html = True
        reason = '第一行 <核实>\r\n第二行 & 信息\r第三行\n' + "长原因" * 100
        await self.notify(reason=reason)
        mail = self.sender.await_args.kwargs
        self.assertIn(reason, mail["text"])
        self.assertIn("第一行 &lt;核实&gt;<br>第二行 &amp; 信息<br>第三行<br>", mail["html"])
        self.assertIn("长原因" * 100, mail["html"])
        self.assertIn("word-break:break-all", mail["html"])

    async def test_initial_group_notice_does_not_wait_for_mail(self):
        sending = asyncio.Event()
        release = asyncio.Event()

        async def send(**kwargs):
            sending.set()
            await release.wait()
            return types.SimpleNamespace(status="sent")

        self.sender.side_effect = send
        first = asyncio.create_task(self.handler(self.bot, self.event))
        await sending.wait()
        self.bot.send_group_msg.assert_awaited_once()
        self.assertIn("挂起待人工审查", self.bot.send_group_msg.await_args.kwargs["message"])
        release.set()
        await first
        self.assertEqual(self.bot.send_group_msg.await_count, 2)
        self.sender.assert_awaited_once()

    async def test_distinct_bot_group_or_flag_gets_distinct_notification(self):
        await self.notify()
        await self.notify(bot_id="another-bot")
        await self.notify(group_id=987)
        await self.notify(request_flag="request-2")
        self.assertEqual(self.sender.await_count, 4)
        keys = [call.kwargs["idempotency_key"] for call in self.sender.await_args_list]
        self.assertEqual(len(set(keys)), 4)
        self.assertTrue(all(call.kwargs["rate_limit_key"] == "qq:789"
                            for call in self.sender.await_args_list))

    async def test_public_dispatcher_status_is_preserved(self):
        for status in ("dry_run", "disabled", "duplicate", "partial", "sent"):
            self.sender.return_value = types.SimpleNamespace(status=status)
            self.assertEqual(await self.notify(), status)

    async def test_unknown_delivery_warns_against_resending(self):
        for code in ("uncertain", "timeout", "connection"):
            self.sender.side_effect = FakeEmailSendError(
                code, "private-secret", delivery_state="unknown"
            )
            self.assertEqual(await self.notify(), "uncertain")
        message = self.notifier.email_status_text("uncertain")
        self.assertIn("不确定", message)
        self.assertIn("勿直接重发", message)
        self.assertNotIn("private-secret", str(self.logger.warning.call_args_list))

    async def test_dispatcher_rate_limit_busy_and_storage_are_distinct(self):
        for code in ("rate_limited", "busy", "storage", "in_progress"):
            self.sender.side_effect = FakeEmailSendError(
                code, "private-secret", delivery_state=(
                    "unknown" if code == "in_progress" else "not_sent"
                )
            )
            self.assertEqual(await self.notify(), code)
        self.assertIn("频率限制", self.notifier.email_status_text("rate_limited"))
        self.assertIn("发送中记录", self.notifier.email_status_text("in_progress"))

    async def test_missing_request_flag_never_sends(self):
        self.assertEqual(await self.notify(request_flag=""), "failed")
        self.sender.assert_not_awaited()

    async def test_initial_group_notice_failure_does_not_skip_email(self):
        self.bot.send_group_msg.side_effect = [RuntimeError("QQ temporarily unavailable"), None]
        await self.handler(self.bot, self.event)
        self.sender.assert_awaited_once()
        self.assertEqual(self.bot.send_group_msg.await_count, 2)

    async def test_mail_status_notice_failure_does_not_resend_email(self):
        self.bot.send_group_msg.side_effect = [None, RuntimeError("QQ temporarily unavailable")]
        await self.handler(self.bot, self.event)
        self.sender.assert_awaited_once()


if __name__ == "__main__":
    unittest.main()

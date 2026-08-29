import unittest
from email.message import EmailMessage
from pathlib import Path
from tempfile import TemporaryDirectory

from emailhub.otp import extract_otp
from emailhub.mail_text import clean_mail_text, collapse_repeated_text, html_to_visible_text
from emailhub.icloud_hme import ICloudHmeClient, ICloudHmeError
from emailhub.server import parse_batch_line, parse_import_line
from emailhub.secrets_store import protect, protect_text, unprotect, unprotect_text
from nimail_server.deployment import (
    _caddy_service_bin_path, caddyfile_text, load_deployment, normalize_domain, save_deployment,
)
from nimail_server.windows_setup import server_task_create_command
from nimail_server.imap_worker import message_text
from nimail_server.database import Database
from nimail_server.viewer_compat import compatibility_cards_html


class ImportTests(unittest.TestCase):
    def test_plain_email(self):
        self.assertEqual(parse_import_line("a@icloud.com"), ("a@icloud.com", "", ""))

    def test_email_service(self):
        self.assertEqual(parse_import_line("a@icloud.com----GitHub"), ("a@icloud.com", "GitHub", ""))

    def test_service_email_cdk(self):
        self.assertEqual(parse_import_line("GitHub----a@icloud.com----GH-1234"), ("a@icloud.com", "GitHub", "GH-1234"))

    def test_invalid_line(self):
        with self.assertRaises(ValueError):
            parse_import_line("not-an-email")

    def test_batch_line(self):
        self.assertEqual(parse_batch_line("GitHub----代码托管"), ("GitHub", "代码托管"))


class ICloudClientTests(unittest.TestCase):
    def test_extract_dsid(self):
        client = ICloudHmeClient("foo=bar; X-APPLE-WEBAUTH-USER=123456%3A0; baz=1", base_url="https://example.test")
        self.assertEqual(client.dsid, "123456")

    def test_missing_dsid(self):
        with self.assertRaises(ICloudHmeError):
            ICloudHmeClient("foo=bar", base_url="https://example.test")


class SecretStoreTests(unittest.TestCase):
    def test_dpapi_roundtrip(self):
        value = "测试凭据-123".encode("utf-8")
        self.assertEqual(unprotect(protect(value)), value)

    def test_dpapi_text_roundtrip(self):
        self.assertEqual(unprotect_text(protect_text("HM-1234-5678")), "HM-1234-5678")


class OtpTests(unittest.TestCase):
    def test_chinese_code(self):
        self.assertEqual(extract_otp("登录验证码", "您的验证码是 482731，十分钟内有效")[0], "482731")

    def test_english_code(self):
        self.assertIsNone(extract_otp("Security code", "Your verification code is AB12CD")[0])

    def test_four_digit_code_without_keyword(self):
        self.assertEqual(extract_otp("hello", "1111 hello@example.com")[0], "1111")

    def test_eight_digit_number_is_not_code(self):
        self.assertIsNone(extract_otp("通知", "订单号 12345678")[0])

    def test_year_is_not_code(self):
        self.assertIsNone(extract_otp("活动通知", "活动日期为 2026 年")[0])


class MailTextTests(unittest.TestCase):
    def test_multipart_alternative_prefers_plain_text(self):
        message = EmailMessage()
        message.set_content("1111\nhello\nhello@example.com")
        message.add_alternative(
            "<p>1111</p><p>hello</p><p>hello@example.com</p>", subtype="html"
        )
        body = message_text(message)
        self.assertEqual(body, "1111\nhello\nhello@example.com")
        self.assertEqual(body.count("1111"), 1)

    def test_existing_repeated_body_is_collapsed(self):
        body = "1111\nhello\na@example.com\n1111\nhello\na@example.com"
        self.assertEqual(collapse_repeated_text(body), "1111\nhello\na@example.com")

    def test_existing_repeated_preview_is_collapsed(self):
        preview = "1111 hello a@example.com 1111 hello a@example.com"
        self.assertEqual(collapse_repeated_text(preview), "1111 hello a@example.com")

    def test_html_email_excludes_css_and_keeps_complete_visible_body(self):
        source = """<html><head><style>@font-face { src: url(font.woff2) }</style></head>
        <body><h1>你的登录验证码</h1><p>验证码是 <strong>548977</strong></p>
        <p>请在 10 分钟内完成验证。</p><script>alert(1)</script></body></html>"""
        text = html_to_visible_text(source)
        self.assertIn("你的登录验证码", text)
        self.assertIn("请在 10 分钟内完成验证。", text)
        self.assertNotIn("@font-face", text)
        self.assertNotIn("alert(1)", text)

    def test_legacy_stored_css_is_removed_when_mail_is_read(self):
        legacy = """你的临时登录代码
@font-face {
font-family: Soehne;
src: url(font.woff2);
}
.ExternalClass,
.ExternalClass div,
.ExternalClass p
{
line-height: 100%;
}
您的验证码是 548977
请在 10 分钟内使用。"""
        cleaned = clean_mail_text(legacy)
        self.assertEqual(cleaned, "你的临时登录代码\n您的验证码是 548977\n请在 10 分钟内使用。")
        self.assertNotIn("font-family", cleaned)


class MessageOrderingTests(unittest.TestCase):
    def test_messages_are_sorted_by_absolute_time_across_timezones(self):
        with TemporaryDirectory() as folder:
            database = Database(Path(folder) / "nimail.db")
            database.init()
            mailbox = database.create_mailbox(
                "alias@icloud.com", "test", "TEST-CDK-1234", None, None, None, "keep"
            )
            database.add_message(
                mailbox["id"], 1, 1, "old", "a@example.com", "old",
                "2026-08-29T21:19:00+00:00", None, 0, "old", "old",
            )
            database.add_message(
                mailbox["id"], 1, 2, "new", "b@example.com", "new",
                "2026-08-29T22:06:00+00:00", None, 0, "new", "new",
            )
            database.add_message(
                mailbox["id"], 1, 3, "middle", "c@example.com", "middle",
                "2026-08-30T05:30:00+08:00", None, 0, "middle", "middle",
            )
            self.assertEqual(
                [item["subject"] for item in database.list_messages(mailbox["id"])],
                ["new", "middle", "old"],
            )


class ViewerCompatibilityTests(unittest.TestCase):
    def test_compatibility_cards_expose_stable_relay_fields(self):
        html = compatibility_cards_html([{
            "id": 7, "sender": "sender@example.com", "subject": "Login",
            "received_at": "2026-08-29T21:36:00+08:00", "otp_code": "482731",
            "preview": "Your code is 482731",
        }], "alias@icloud.com")
        self.assertIn('<article class="mail-card">', html)
        self.assertIn('<span class="subject">Login</span>', html)
        self.assertIn('<span class="date">2026-08-29 21:36:00</span>', html)
        self.assertIn('<div class="meta">发件人：sender@example.com</div>', html)
        self.assertIn('<pre class="body">Your code is 482731</pre>', html)

    def test_compatibility_cards_escape_untrusted_mail_content(self):
        html = compatibility_cards_html([{"sender": '<script>alert(1)</script>'}])
        self.assertNotIn("<script>", html)
        self.assertIn("&lt;script&gt;", html)


class DeploymentTests(unittest.TestCase):
    def test_normalize_domain(self):
        self.assertEqual(normalize_domain("https://Mail.Example.com/"), "mail.example.com")

    def test_reject_domain_with_path(self):
        with self.assertRaises(ValueError):
            normalize_domain("mail.example.com/c/test")

    def test_save_and_load_server_deployment(self):
        with TemporaryDirectory() as folder:
            saved = save_deployment(Path(folder), "mail.example.com")
            self.assertEqual(saved["viewer_base_url"], "https://mail.example.com")
            self.assertEqual(load_deployment(Path(folder))["mode"], "server")

    def test_caddy_only_exposes_public_routes(self):
        config = caddyfile_text("mail.example.com")
        self.assertIn("/api/public/c/*", config)
        self.assertIn("disable_http_challenge", config)
        self.assertIn("auto_https disable_redirects", config)
        self.assertNotIn("/api/admin", config)

    def test_caddy_service_command_quotes_paths(self):
        command = _caddy_service_bin_path(
            Path(r"C:\Program Files\NIMAIL\caddy.exe"),
            Path(r"C:\Program Files\NIMAIL\Caddyfile"),
        )
        self.assertEqual(
            command,
            '"C:\\Program Files\\NIMAIL\\caddy.exe" run --config '
            '"C:\\Program Files\\NIMAIL\\Caddyfile" --adapter caddyfile',
        )

    def test_server_task_uses_argument_for_program_files_path(self):
        command = server_task_create_command(Path(r"C:\Program Files\NIMAIL\NIMAIL-Server.exe"))
        self.assertEqual(command[0], "schtasks.exe")
        self.assertEqual(command[command.index("/TR") + 1], r"C:\Program Files\NIMAIL\NIMAIL-Server.exe")
        self.assertIn("SYSTEM", command)


if __name__ == "__main__":
    unittest.main()

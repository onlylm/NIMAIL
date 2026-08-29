from __future__ import annotations

import email
import imaplib
import re
import threading
from datetime import datetime, timezone
from email.header import decode_header, make_header
from email.utils import parsedate_to_datetime

from emailhub.otp import extract_otp
from emailhub.mail_text import clean_mail_text, html_to_visible_text

from .database import Database
from .security import iso_utc


def decoded_header(value: str | None) -> str:
    if not value:
        return ""
    try:
        return str(make_header(decode_header(value)))
    except Exception:
        return value


def message_text(message: email.message.Message) -> str:
    plain_parts = []
    html_parts = []
    for part in message.walk() if message.is_multipart() else [message]:
        if part.get_content_maintype() == "multipart" or part.get_filename():
            continue
        content_type = part.get_content_type()
        if content_type not in ("text/plain", "text/html"):
            continue
        payload = part.get_payload(decode=True) or b""
        try:
            text = payload.decode(part.get_content_charset() or "utf-8", errors="replace")
        except LookupError:
            text = payload.decode("utf-8", errors="replace")
        if content_type == "text/plain":
            plain_parts.append(text)
        else:
            html_parts.append(html_to_visible_text(text))
    # multipart/alternative contains the same content twice. Prefer text/plain and
    # use HTML only when a plain representation is unavailable.
    return clean_mail_text("\n".join(plain_parts or html_parts))


def uidvalidity(client) -> int:
    status, values = client.response("UIDVALIDITY")
    if status == "UIDVALIDITY" and values:
        match = re.search(rb"\d+", values[0] or b"0")
        return int(match.group(0)) if match else 0
    return 0


class ImapService:
    def __init__(self, db: Database):
        self.db = db
        self.last_sync = db.get_setting("imap_last_sync", "")
        self.last_error = db.get_setting("imap_last_error", "")
        self._lock = threading.Lock()

    @property
    def configured(self):
        return bool(self.db.get_setting("imap_email") and self.db.get_setting("imap_app_password"))

    @property
    def email_address(self):
        return self.db.get_setting("imap_email", "")

    def _login(self, address: str, password: str):
        client = imaplib.IMAP4_SSL("imap.mail.me.com", 993, timeout=30)
        client.login(address, password)
        return client

    def configure(self, address: str, password: str, test: bool = True):
        if test:
            client = self._login(address, password)
            client.logout()
        self.db.set_setting("imap_email", address)
        self.db.set_setting("imap_app_password", password, encrypted=True)
        self.last_error = ""
        self.db.set_setting("imap_last_error", "")

    def sync(self):
        if not self._lock.acquire(blocking=False):
            return {"running": True, "checked": 0, "added": 0, "skipped": 0, "failed": 0}
        try:
            address = self.db.get_setting("imap_email", "")
            password = self.db.get_setting("imap_app_password", "")
            if not address or not password:
                raise RuntimeError("请先配置 iCloud IMAP")
            client = self._login(address, password)
            try:
                status, _ = client.select("INBOX", readonly=True)
                if status != "OK":
                    raise RuntimeError("无法打开 iCloud 收件箱")
                current_validity = uidvalidity(client)
                old_validity, last_uid = self.db.sync_state()
                if current_validity and old_validity and current_validity != old_validity:
                    last_uid = 0
                status, data = client.uid("search", None, f"UID {last_uid + 1}:*")
                if status != "OK":
                    raise RuntimeError("无法搜索 iCloud 邮件")
                uids = [int(value) for value in (data[0] or b"").split()]
                added = skipped = failed = 0
                for uid in uids:
                    try:
                        if self._process(client, current_validity, uid):
                            added += 1
                        else:
                            skipped += 1
                    except Exception:
                        failed += 1
                        break
                    last_uid = max(last_uid, uid)
                    self.db.set_sync_state(current_validity, last_uid)
                self.last_sync, self.last_error = iso_utc(), ""
                self.db.set_setting("imap_last_sync", self.last_sync)
                self.db.set_setting("imap_last_error", "")
                return {"running": False, "checked": len(uids), "added": added,
                        "skipped": skipped, "failed": failed, "uidvalidity": current_validity,
                        "last_uid": last_uid}
            finally:
                try:
                    client.logout()
                except Exception:
                    pass
        except Exception as exc:
            self.last_error = str(exc)
            self.db.set_setting("imap_last_error", self.last_error)
            raise
        finally:
            self._lock.release()

    def _process(self, client, validity: int, uid: int) -> bool:
        status, fetched = client.uid("fetch", str(uid), "(BODY.PEEK[])")
        if status != "OK":
            status, fetched = client.uid("fetch", str(uid), "(RFC822)")
        raw = next((part[1] for part in fetched if isinstance(part, tuple) and len(part) > 1
                    and isinstance(part[1], (bytes, bytearray))), None)
        if status != "OK" or not raw:
            raise RuntimeError(f"读取邮件 UID {uid} 失败")
        message = email.message_from_bytes(raw)
        body = message_text(message)
        headers = "\n".join(
            decoded_header(value) for name, value in message.items()
            if name.lower() in {"to", "cc", "delivered-to", "x-original-to", "envelope-to",
                                "original-recipient", "x-original-recipient", "x-envelope-to",
                                "resent-to", "x-forwarded-to", "x-apple-original-to"}
        )
        mailbox = self.db.mailbox_by_address_text(headers + "\n" + body)
        if not mailbox:
            return False
        subject, sender = decoded_header(message.get("Subject")), decoded_header(message.get("From"))
        code, confidence = extract_otp(subject, body)
        try:
            received = parsedate_to_datetime(message.get("Date")) if message.get("Date") else datetime.now(timezone.utc)
            if received.tzinfo is None:
                received = received.replace(tzinfo=timezone.utc)
        except Exception:
            received = datetime.now(timezone.utc)
        clean_body = "\n".join(line.strip() for line in body.splitlines() if line.strip())
        return self.db.add_message(
            mailbox["id"], validity, uid, message.get("Message-ID", ""), sender, subject,
            received.isoformat(), code, confidence, " ".join(clean_body.split())[:500], clean_body,
        )

from __future__ import annotations

import secrets
import sqlite3
from contextlib import contextmanager
from datetime import datetime, timedelta
from pathlib import Path

from emailhub.mail_text import clean_mail_text
from emailhub.otp import extract_otp

from .crypto import protect_text, unprotect_text
from .security import hash_secret, iso_utc


RANDOM_LABEL_ALPHABET = "ABCDEFGHJKLMNPQRSTUVWXYZabcdefghijkmnopqrstuvwxyz23456789"


def generate_random_label(existing: set[str] | None = None) -> str:
    if existing is None:
        existing = set()
    while True:
        length = 10 + secrets.randbelow(9)
        value = "".join(secrets.choice(RANDOM_LABEL_ALPHABET) for _ in range(length))
        if value not in existing:
            return value


def parse_time(value: str | None) -> datetime | None:
    return datetime.fromisoformat(value.replace("Z", "+00:00")) if value else None


def add_seconds(value: str | None, seconds: int | None) -> str | None:
    base = parse_time(value)
    return (base + timedelta(seconds=seconds)).isoformat() if base and seconds is not None else None


class Database:
    def __init__(self, path: Path):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)

    @contextmanager
    def connect(self):
        conn = sqlite3.connect(self.path, timeout=30)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys=ON")
        conn.execute("PRAGMA busy_timeout=30000")
        try:
            yield conn
            conn.commit()
        finally:
            conn.close()

    def init(self) -> None:
        with self.connect() as conn:
            conn.execute("PRAGMA journal_mode=WAL")
            conn.executescript(
                """
                CREATE TABLE IF NOT EXISTS admins (
                    id INTEGER PRIMARY KEY CHECK(id=1), username TEXT NOT NULL UNIQUE COLLATE NOCASE,
                    password_hash TEXT NOT NULL, created_at TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS sessions (
                    id INTEGER PRIMARY KEY AUTOINCREMENT, token_hash TEXT NOT NULL UNIQUE,
                    created_at TEXT NOT NULL, expires_at TEXT NOT NULL, last_seen_at TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS settings (
                    key TEXT PRIMARY KEY, value TEXT NOT NULL, encrypted INTEGER NOT NULL DEFAULT 0,
                    updated_at TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS mailboxes (
                    id TEXT PRIMARY KEY, address TEXT NOT NULL UNIQUE COLLATE NOCASE,
                    service_name TEXT NOT NULL DEFAULT '', cdk_hash TEXT UNIQUE, cdk_secret TEXT,
                    state TEXT NOT NULL DEFAULT 'active', apple_state TEXT NOT NULL DEFAULT 'active',
                    apple_action TEXT NOT NULL DEFAULT 'deactivate', created_at TEXT NOT NULL,
                    first_message_at TEXT, deactivate_after_seconds INTEGER, deactivate_due_at TEXT,
                    message_retention_seconds INTEGER, purge_due_at TEXT,
                    cdk_retention_seconds INTEGER, cdk_expires_at TEXT, deactivated_at TEXT,
                    messages_purged_at TEXT, lifecycle_retry_at TEXT,
                    last_lifecycle_error TEXT NOT NULL DEFAULT ''
                );
                CREATE TABLE IF NOT EXISTS messages (
                    id INTEGER PRIMARY KEY AUTOINCREMENT, mailbox_id TEXT NOT NULL,
                    uidvalidity INTEGER NOT NULL, imap_uid INTEGER NOT NULL,
                    message_id TEXT NOT NULL DEFAULT '', sender TEXT NOT NULL DEFAULT '',
                    subject TEXT NOT NULL DEFAULT '', received_at TEXT NOT NULL, otp_code TEXT,
                    otp_confidence REAL NOT NULL DEFAULT 0, preview TEXT NOT NULL DEFAULT '',
                    body_text TEXT NOT NULL DEFAULT '', created_at TEXT NOT NULL,
                    UNIQUE(uidvalidity,imap_uid),
                    FOREIGN KEY(mailbox_id) REFERENCES mailboxes(id) ON DELETE CASCADE
                );
                CREATE TABLE IF NOT EXISTS batch_jobs (
                    id TEXT PRIMARY KEY, requested_count INTEGER NOT NULL, label_prefix TEXT NOT NULL,
                    note TEXT NOT NULL DEFAULT '', interval_seconds INTEGER NOT NULL,
                    deactivate_after_seconds INTEGER, message_retention_seconds INTEGER,
                    cdk_retention_seconds INTEGER, apple_action TEXT NOT NULL,
                    state TEXT NOT NULL DEFAULT 'queued', created_at TEXT NOT NULL,
                    started_at TEXT, finished_at TEXT, error TEXT NOT NULL DEFAULT ''
                );
                CREATE TABLE IF NOT EXISTS batch_items (
                    id INTEGER PRIMARY KEY AUTOINCREMENT, job_id TEXT NOT NULL, position INTEGER NOT NULL,
                    label TEXT NOT NULL, state TEXT NOT NULL DEFAULT 'waiting', address TEXT NOT NULL DEFAULT '',
                    mailbox_id TEXT, error TEXT NOT NULL DEFAULT '', started_at TEXT, finished_at TEXT,
                    UNIQUE(job_id,position), FOREIGN KEY(job_id) REFERENCES batch_jobs(id) ON DELETE CASCADE,
                    FOREIGN KEY(mailbox_id) REFERENCES mailboxes(id) ON DELETE SET NULL
                );
                CREATE TABLE IF NOT EXISTS audit_log (
                    id INTEGER PRIMARY KEY AUTOINCREMENT, action TEXT NOT NULL,
                    target_type TEXT NOT NULL DEFAULT '', target_id TEXT NOT NULL DEFAULT '',
                    detail TEXT NOT NULL DEFAULT '', created_at TEXT NOT NULL
                );
                CREATE INDEX IF NOT EXISTS idx_messages_mailbox_received
                    ON messages(mailbox_id,received_at DESC);
                CREATE INDEX IF NOT EXISTS idx_mailboxes_cdk_hash ON mailboxes(cdk_hash);
                """
            )
            conn.execute(
                """UPDATE batch_jobs SET state='failed',finished_at=?,
                error='服务器在任务执行期间重新启动，请重新发起未完成部分'
                WHERE state IN ('queued','running')""", (iso_utc(),)
            )

    def _audit(self, conn, action: str, target_type: str, target_id: str, detail: str = ""):
        conn.execute(
            "INSERT INTO audit_log(action,target_type,target_id,detail,created_at) VALUES(?,?,?,?,?)",
            (action, target_type, target_id, detail[:500], iso_utc()),
        )

    def admin_exists(self) -> bool:
        with self.connect() as conn:
            return conn.execute("SELECT 1 FROM admins WHERE id=1").fetchone() is not None

    def create_admin(self, username: str, password_hash: str) -> None:
        with self.connect() as conn:
            conn.execute(
                "INSERT INTO admins(id,username,password_hash,created_at) VALUES(1,?,?,?)",
                (username.strip(), password_hash, iso_utc()),
            )
            self._audit(conn, "admin.bootstrap", "admin", "1")

    def get_admin(self, username: str | None = None):
        query, params = "SELECT * FROM admins WHERE id=1", ()
        if username is not None:
            query += " AND username=? COLLATE NOCASE"
            params = (username.strip(),)
        with self.connect() as conn:
            row = conn.execute(query, params).fetchone()
            return dict(row) if row else None

    def create_session(self, token_hash: str, expires_at: str) -> None:
        now = iso_utc()
        with self.connect() as conn:
            conn.execute(
                "INSERT INTO sessions(token_hash,created_at,expires_at,last_seen_at) VALUES(?,?,?,?)",
                (token_hash, now, expires_at, now),
            )
            conn.execute("DELETE FROM sessions WHERE expires_at<=?", (now,))

    def validate_session(self, token_hash: str) -> bool:
        now = iso_utc()
        with self.connect() as conn:
            row = conn.execute(
                "SELECT id FROM sessions WHERE token_hash=? AND expires_at>?", (token_hash, now)
            ).fetchone()
            if not row:
                return False
            conn.execute("UPDATE sessions SET last_seen_at=? WHERE id=?", (now, row["id"]))
            return True

    def delete_session(self, token_hash: str) -> None:
        with self.connect() as conn:
            conn.execute("DELETE FROM sessions WHERE token_hash=?", (token_hash,))

    def set_setting(self, key: str, value: str, encrypted: bool = False) -> None:
        stored = protect_text(value) if encrypted and value else value
        with self.connect() as conn:
            conn.execute(
                """INSERT INTO settings(key,value,encrypted,updated_at) VALUES(?,?,?,?)
                ON CONFLICT(key) DO UPDATE SET value=excluded.value,encrypted=excluded.encrypted,
                updated_at=excluded.updated_at""", (key, stored, int(encrypted), iso_utc())
            )

    def get_setting(self, key: str, default: str = "") -> str:
        with self.connect() as conn:
            row = conn.execute("SELECT value,encrypted FROM settings WHERE key=?", (key,)).fetchone()
        if not row:
            return default
        return unprotect_text(row["value"]) if row["encrypted"] else row["value"]

    def create_mailbox(
        self, address: str, service_name: str, cdk: str,
        deactivate_after_seconds: int | None, message_retention_seconds: int | None,
        cdk_retention_seconds: int | None, apple_action: str,
    ) -> dict:
        mailbox_id = secrets.token_urlsafe(9)
        with self.connect() as conn:
            conn.execute(
                """INSERT INTO mailboxes(id,address,service_name,cdk_hash,cdk_secret,created_at,
                deactivate_after_seconds,message_retention_seconds,cdk_retention_seconds,apple_action)
                VALUES(?,?,?,?,?,?,?,?,?,?)""",
                (mailbox_id, address.strip().lower(), service_name.strip(), hash_secret(cdk),
                 protect_text(cdk), iso_utc(), deactivate_after_seconds, message_retention_seconds,
                 cdk_retention_seconds, apple_action),
            )
            self._audit(conn, "mailbox.create", "mailbox", mailbox_id, service_name)
        return self.get_mailbox(mailbox_id, include_cdk=True)

    def _clean_mailbox(self, row, include_cdk: bool = False) -> dict:
        item = dict(row)
        if include_cdk:
            item["cdk"] = unprotect_text(item.get("cdk_secret") or "")
        item.pop("cdk_secret", None)
        item.pop("cdk_hash", None)
        return item

    def get_mailbox(self, mailbox_id: str, include_cdk: bool = False):
        with self.connect() as conn:
            row = conn.execute("SELECT * FROM mailboxes WHERE id=?", (mailbox_id,)).fetchone()
            if not row:
                return None
            count = conn.execute("SELECT COUNT(*) FROM messages WHERE mailbox_id=?", (mailbox_id,)).fetchone()[0]
        item = self._clean_mailbox(row, include_cdk)
        item["message_count"] = count
        return item

    def list_mailboxes(self, include_cdk: bool = True) -> list[dict]:
        with self.connect() as conn:
            rows = conn.execute(
                """SELECT b.*,(SELECT COUNT(*) FROM messages m WHERE m.mailbox_id=b.id) message_count,
                (SELECT received_at FROM messages m WHERE m.mailbox_id=b.id
                 ORDER BY julianday(received_at) DESC,m.id DESC LIMIT 1) last_message_at
                FROM mailboxes b ORDER BY b.created_at DESC"""
            ).fetchall()
        return [self._clean_mailbox(row, include_cdk) for row in rows]

    def mailbox_by_address_text(self, text: str):
        lowered = text.lower()
        with self.connect() as conn:
            rows = conn.execute("SELECT id,address,service_name FROM mailboxes WHERE state!='deleted'").fetchall()
        return next((dict(row) for row in rows if row["address"].lower() in lowered), None)

    def mailbox_by_cdk(self, cdk: str):
        now = iso_utc()
        with self.connect() as conn:
            row = conn.execute(
                """SELECT * FROM mailboxes WHERE cdk_hash=? AND state!='deleted'
                AND (cdk_expires_at IS NULL OR cdk_expires_at>?)""",
                (hash_secret(cdk.strip().upper()), now),
            ).fetchone()
            if not row:
                return None
            count = conn.execute("SELECT COUNT(*) FROM messages WHERE mailbox_id=?", (row["id"],)).fetchone()[0]
        item = self._clean_mailbox(row)
        item["message_count"] = count
        return item

    def rotate_cdk(self, mailbox_id: str, cdk: str) -> bool:
        with self.connect() as conn:
            result = conn.execute(
                "UPDATE mailboxes SET cdk_hash=?,cdk_secret=?,cdk_expires_at=NULL WHERE id=?",
                (hash_secret(cdk), protect_text(cdk), mailbox_id),
            )
            if result.rowcount:
                self._audit(conn, "cdk.rotate", "mailbox", mailbox_id)
            return bool(result.rowcount)

    def delete_mailbox(self, mailbox_id: str) -> bool:
        with self.connect() as conn:
            result = conn.execute("DELETE FROM mailboxes WHERE id=?", (mailbox_id,))
            if result.rowcount:
                self._audit(conn, "mailbox.delete", "mailbox", mailbox_id)
            return bool(result.rowcount)

    def update_policy(
        self, mailbox_id: str, deactivate_after_seconds: int | None,
        message_retention_seconds: int | None, cdk_retention_seconds: int | None,
        apple_action: str,
    ) -> bool:
        with self.connect() as conn:
            row = conn.execute("SELECT first_message_at FROM mailboxes WHERE id=?", (mailbox_id,)).fetchone()
            if not row:
                return False
            first = row["first_message_at"]
            result = conn.execute(
                """UPDATE mailboxes SET deactivate_after_seconds=?,message_retention_seconds=?,
                cdk_retention_seconds=?,apple_action=?,deactivate_due_at=?,purge_due_at=?,cdk_expires_at=?
                WHERE id=?""",
                (deactivate_after_seconds, message_retention_seconds, cdk_retention_seconds, apple_action,
                 add_seconds(first, deactivate_after_seconds), add_seconds(first, message_retention_seconds),
                 add_seconds(first, cdk_retention_seconds), mailbox_id),
            )
            self._audit(conn, "mailbox.policy", "mailbox", mailbox_id, apple_action)
            return bool(result.rowcount)

    def add_message(
        self, mailbox_id: str, uidvalidity: int, imap_uid: int, message_id: str,
        sender: str, subject: str, received_at: str, otp_code: str | None,
        otp_confidence: float, preview: str, body_text: str,
    ) -> bool:
        body_text = clean_mail_text(body_text)
        preview = clean_mail_text(preview)
        try:
            with self.connect() as conn:
                conn.execute(
                    """INSERT INTO messages(mailbox_id,uidvalidity,imap_uid,message_id,sender,subject,
                    received_at,otp_code,otp_confidence,preview,body_text,created_at)
                    VALUES(?,?,?,?,?,?,?,?,?,?,?,?)""",
                    (mailbox_id, uidvalidity, imap_uid, message_id, sender, subject, received_at,
                     otp_code, otp_confidence, preview[:500], body_text[:100000], iso_utc()),
                )
                row = conn.execute(
                    """SELECT first_message_at,deactivate_after_seconds,message_retention_seconds,
                    cdk_retention_seconds FROM mailboxes WHERE id=?""", (mailbox_id,)
                ).fetchone()
                if row and not row["first_message_at"]:
                    conn.execute(
                        """UPDATE mailboxes SET first_message_at=?,deactivate_due_at=?,purge_due_at=?,
                        cdk_expires_at=? WHERE id=?""",
                        (received_at, add_seconds(received_at, row["deactivate_after_seconds"]),
                         add_seconds(received_at, row["message_retention_seconds"]),
                         add_seconds(received_at, row["cdk_retention_seconds"]), mailbox_id),
                    )
            return True
        except sqlite3.IntegrityError:
            return False

    def list_messages(self, mailbox_id: str, limit: int = 50, include_body: bool = False) -> list[dict]:
        columns = "id,mailbox_id,sender,subject,received_at,otp_code,otp_confidence,preview"
        if include_body:
            columns += ",body_text"
        with self.connect() as conn:
            rows = conn.execute(
                f"SELECT {columns} FROM messages WHERE mailbox_id=? "
                "ORDER BY julianday(received_at) DESC,id DESC LIMIT ?",
                (mailbox_id, min(max(limit, 1), 100)),
            ).fetchall()
        items = [dict(row) for row in rows]
        for item in items:
            item["preview"] = clean_mail_text(item.get("preview") or "")
            if "body_text" in item:
                item["body_text"] = clean_mail_text(item.get("body_text") or "")
            if not item.get("otp_code"):
                code, confidence = extract_otp(
                    item.get("subject") or "", item.get("body_text") or item["preview"]
                )
                item["otp_code"], item["otp_confidence"] = code, confidence
        return items

    def get_message(self, mailbox_id: str, message_id: int):
        with self.connect() as conn:
            row = conn.execute(
                """SELECT id,mailbox_id,sender,subject,received_at,otp_code,otp_confidence,preview,body_text
                FROM messages WHERE id=? AND mailbox_id=?""", (message_id, mailbox_id)
            ).fetchone()
        if not row:
            return None
        item = dict(row)
        item["preview"] = clean_mail_text(item.get("preview") or "")
        item["body_text"] = clean_mail_text(item.get("body_text") or "")
        if not item.get("otp_code"):
            code, confidence = extract_otp(
                item.get("subject") or "", item["body_text"] or item["preview"]
            )
            item["otp_code"], item["otp_confidence"] = code, confidence
        return item

    def lifecycle_due(self, now: str | None = None) -> list[dict]:
        now = now or iso_utc()
        with self.connect() as conn:
            rows = conn.execute(
                """SELECT * FROM mailboxes WHERE state!='deleted' AND (
                (deactivate_due_at IS NOT NULL AND deactivate_due_at<=? AND deactivated_at IS NULL
                 AND apple_action!='keep' AND (lifecycle_retry_at IS NULL OR lifecycle_retry_at<=?))
                OR (purge_due_at IS NOT NULL AND purge_due_at<=? AND messages_purged_at IS NULL)
                OR (cdk_expires_at IS NOT NULL AND cdk_expires_at<=? AND cdk_hash IS NOT NULL))""",
                (now, now, now, now),
            ).fetchall()
        return [dict(row) for row in rows]

    def apply_local_lifecycle(self, mailbox_id: str, now: str | None = None) -> dict:
        now = now or iso_utc()
        result = {"cdk_expired": False, "messages_purged": False, "deactivation_pending": False}
        with self.connect() as conn:
            row = conn.execute("SELECT * FROM mailboxes WHERE id=?", (mailbox_id,)).fetchone()
            if not row:
                return result
            if row["cdk_expires_at"] and row["cdk_expires_at"] <= now and row["cdk_hash"]:
                conn.execute("UPDATE mailboxes SET cdk_hash=NULL WHERE id=?", (mailbox_id,))
                result["cdk_expired"] = True
            if row["purge_due_at"] and row["purge_due_at"] <= now and not row["messages_purged_at"]:
                conn.execute("DELETE FROM messages WHERE mailbox_id=?", (mailbox_id,))
                conn.execute("UPDATE mailboxes SET messages_purged_at=? WHERE id=?", (now, mailbox_id))
                result["messages_purged"] = True
            if (row["deactivate_due_at"] and row["deactivate_due_at"] <= now
                    and not row["deactivated_at"] and row["apple_state"] != "pending"):
                conn.execute(
                    "UPDATE mailboxes SET state='deactivation_pending',apple_state='pending' WHERE id=?",
                    (mailbox_id,),
                )
                result["deactivation_pending"] = True
            if any(result.values()):
                self._audit(conn, "mailbox.lifecycle", "mailbox", mailbox_id, str(result))
        return result

    def complete_apple_lifecycle(self, mailbox_id: str, action: str) -> None:
        state = "deleted" if action == "delete" else "inactive"
        apple_state = "deleted" if action == "delete" else "deactivated"
        with self.connect() as conn:
            conn.execute(
                """UPDATE mailboxes SET state=?,apple_state=?,deactivated_at=?,lifecycle_retry_at=NULL,
                last_lifecycle_error='' WHERE id=?""", (state, apple_state, iso_utc(), mailbox_id)
            )
            self._audit(conn, f"apple.{action}", "mailbox", mailbox_id)

    def defer_apple_lifecycle(self, mailbox_id: str, error: str, retry_seconds: int = 300) -> None:
        with self.connect() as conn:
            conn.execute(
                """UPDATE mailboxes SET state='deactivation_pending',apple_state='pending',
                lifecycle_retry_at=?,last_lifecycle_error=? WHERE id=?""",
                (add_seconds(iso_utc(), retry_seconds), error[:500], mailbox_id),
            )

    def set_sync_state(self, uidvalidity: int, last_uid: int) -> None:
        self.set_setting("imap_uidvalidity", str(uidvalidity))
        self.set_setting("imap_last_uid", str(last_uid))

    def sync_state(self) -> tuple[int, int]:
        return int(self.get_setting("imap_uidvalidity", "0") or 0), int(self.get_setting("imap_last_uid", "0") or 0)

    def create_batch_job(
        self, count: int, label_prefix: str, note: str, interval_seconds: int,
        deactivate_after_seconds: int | None, message_retention_seconds: int | None,
        cdk_retention_seconds: int | None, apple_action: str,
    ) -> dict:
        job_id, created_at = secrets.token_urlsafe(10), iso_utc()
        with self.connect() as conn:
            if conn.execute("SELECT 1 FROM batch_jobs WHERE state IN ('queued','running') LIMIT 1").fetchone():
                raise RuntimeError("已有批量创建任务正在运行")
            conn.execute(
                """INSERT INTO batch_jobs(id,requested_count,label_prefix,note,interval_seconds,
                deactivate_after_seconds,message_retention_seconds,cdk_retention_seconds,apple_action,state,created_at)
                VALUES(?,?,?,?,?,?,?,?,?,'queued',?)""",
                (job_id, count, label_prefix, note, interval_seconds, deactivate_after_seconds,
                 message_retention_seconds, cdk_retention_seconds, apple_action, created_at),
            )
            used_labels: set[str] = set()
            for position in range(1, count + 1):
                random_label = generate_random_label(used_labels)
                used_labels.add(random_label)
                conn.execute(
                    "INSERT INTO batch_items(job_id,position,label) VALUES(?,?,?)",
                    (job_id, position, random_label),
                )
            self._audit(conn, "batch.create", "batch_job", job_id, f"count={count}")
        return self.get_batch_job(job_id)

    def get_batch_job(self, job_id: str) -> dict | None:
        with self.connect() as conn:
            row = conn.execute("SELECT * FROM batch_jobs WHERE id=?", (job_id,)).fetchone()
            if not row:
                return None
            item_rows = conn.execute("SELECT * FROM batch_items WHERE job_id=? ORDER BY position", (job_id,)).fetchall()
        job, items = dict(row), []
        for item_row in item_rows:
            item = dict(item_row)
            if item.get("mailbox_id"):
                mailbox = self.get_mailbox(item["mailbox_id"], include_cdk=True)
                if mailbox:
                    item["cdk"] = mailbox.get("cdk", "")
            items.append(item)
        job["items"] = items
        job["success_count"] = sum(i["state"] == "success" for i in items)
        job["failed_count"] = sum(i["state"] == "failed" for i in items)
        job["completed_count"] = sum(i["state"] in ("success", "failed", "cancelled") for i in items)
        return job

    def latest_batch_job(self) -> dict | None:
        with self.connect() as conn:
            row = conn.execute("SELECT id FROM batch_jobs ORDER BY created_at DESC LIMIT 1").fetchone()
        return self.get_batch_job(row["id"]) if row else None

    def mark_batch_running(self, job_id: str) -> None:
        with self.connect() as conn:
            conn.execute("UPDATE batch_jobs SET state='running',started_at=? WHERE id=?", (iso_utc(), job_id))

    def mark_batch_item_running(self, job_id: str, position: int) -> None:
        with self.connect() as conn:
            conn.execute(
                "UPDATE batch_items SET state='creating',started_at=? WHERE job_id=? AND position=?",
                (iso_utc(), job_id, position),
            )

    def mark_batch_item_success(self, job_id: str, position: int, address: str, mailbox_id: str) -> None:
        with self.connect() as conn:
            conn.execute(
                """UPDATE batch_items SET state='success',address=?,mailbox_id=?,finished_at=?
                WHERE job_id=? AND position=?""", (address, mailbox_id, iso_utc(), job_id, position)
            )

    def fail_batch_job(self, job_id: str, position: int, error: str) -> None:
        now = iso_utc()
        with self.connect() as conn:
            conn.execute(
                "UPDATE batch_items SET state='failed',error=?,finished_at=? WHERE job_id=? AND position=?",
                (error[:500], now, job_id, position),
            )
            conn.execute(
                """UPDATE batch_items SET state='cancelled',error='前序创建失败，任务已停止',finished_at=?
                WHERE job_id=? AND state='waiting'""", (now, job_id)
            )
            conn.execute(
                "UPDATE batch_jobs SET state='failed',finished_at=?,error=? WHERE id=?",
                (now, error[:500], job_id),
            )

    def complete_batch_job(self, job_id: str) -> None:
        with self.connect() as conn:
            conn.execute("UPDATE batch_jobs SET state='completed',finished_at=? WHERE id=?", (iso_utc(), job_id))
            self._audit(conn, "batch.completed", "batch_job", job_id)

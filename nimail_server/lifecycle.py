from __future__ import annotations

import threading
import time

from .database import Database


class LifecycleService:
    def __init__(self, db: Database, apple_service=None):
        self.db = db
        self.apple_service = apple_service
        self.last_result = {"checked": 0, "changed": 0, "details": []}

    def run_once(self) -> dict:
        due, details, changed = self.db.lifecycle_due(), [], 0
        for mailbox in due:
            result = self.db.apply_local_lifecycle(mailbox["id"])
            if (mailbox.get("deactivate_due_at") and not mailbox.get("deactivated_at")
                    and mailbox.get("apple_action") in ("deactivate", "delete")):
                if self.apple_service and self.apple_service.configured:
                    try:
                        self.apple_service.apply_lifecycle(mailbox["address"], mailbox["apple_action"])
                        self.db.complete_apple_lifecycle(mailbox["id"], mailbox["apple_action"])
                        result["apple_completed"] = True
                    except Exception as exc:
                        self.db.defer_apple_lifecycle(mailbox["id"], str(exc))
                        result["apple_deferred"] = True
                else:
                    self.db.defer_apple_lifecycle(mailbox["id"], "等待有效的 Apple 会话执行操作")
                    result["apple_deferred"] = True
            if any(result.values()):
                changed += 1
                details.append({"mailbox_id": mailbox["id"], **result})
        self.last_result = {"checked": len(due), "changed": changed, "details": details}
        return self.last_result


class BackgroundWorkers:
    IMAP_INTERVAL_SECONDS = 4
    LIFECYCLE_INTERVAL_SECONDS = 5

    def __init__(self, imap_service, lifecycle_service: LifecycleService):
        self.imap_service = imap_service
        self.lifecycle_service = lifecycle_service
        self.stop_event = threading.Event()
        self.thread = None

    def start(self):
        if self.thread and self.thread.is_alive():
            return
        self.thread = threading.Thread(target=self._run, daemon=True, name="nimail-background")
        self.thread.start()

    def stop(self):
        self.stop_event.set()
        if self.thread:
            self.thread.join(timeout=5)

    def _run(self):
        # Check mail immediately after startup, then use short incremental polling.
        # A 20-second interval plus Apple relay latency could exceed a client's
        # 60-second OTP timeout, especially for a second verification message.
        next_imap = 0.0
        next_lifecycle = 0.0
        while not self.stop_event.wait(1):
            now = time.monotonic()
            if now >= next_lifecycle:
                try:
                    self.lifecycle_service.run_once()
                except Exception:
                    pass
                next_lifecycle = time.monotonic() + self.LIFECYCLE_INTERVAL_SECONDS
            if now >= next_imap and self.imap_service.configured:
                try:
                    self.imap_service.sync()
                except Exception:
                    pass
                next_imap = time.monotonic() + self.IMAP_INTERVAL_SECONDS

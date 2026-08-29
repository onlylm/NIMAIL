from __future__ import annotations

import threading
import time

from .database import Database
from .security import generate_cdk


class BatchCreateService:
    def __init__(self, db: Database, apple_service):
        self.db = db
        self.apple_service = apple_service
        self._lock = threading.Lock()
        self._threads: dict[str, threading.Thread] = {}

    def start(self, payload) -> dict:
        if not self.apple_service.configured:
            raise RuntimeError("请先配置并验证 Apple 网页会话")
        with self._lock:
            job = self.db.create_batch_job(
                payload.count, payload.label_prefix, payload.note, payload.interval_seconds,
                payload.deactivate_after_seconds, payload.message_retention_seconds,
                payload.cdk_retention_seconds, payload.apple_action,
            )
            thread = threading.Thread(
                target=self._run, args=(job["id"],), name=f"nimail-batch-{job['id']}", daemon=True
            )
            self._threads[job["id"]] = thread
            thread.start()
            return job

    def wait(self, job_id: str, timeout: float = 30) -> None:
        thread = self._threads.get(job_id)
        if thread:
            thread.join(timeout=timeout)

    def _run(self, job_id: str) -> None:
        job = self.db.get_batch_job(job_id)
        if not job:
            return
        self.db.mark_batch_running(job_id)
        for index, item in enumerate(job["items"]):
            position = item["position"]
            self.db.mark_batch_item_running(job_id, position)
            try:
                address = self.apple_service.create_alias(item["label"], job["note"])
                mailbox = self.db.create_mailbox(
                    address, item["label"], generate_cdk(), job["deactivate_after_seconds"],
                    job["message_retention_seconds"], job["cdk_retention_seconds"], job["apple_action"],
                )
                self.db.mark_batch_item_success(job_id, position, address, mailbox["id"])
            except Exception as exc:
                self.db.fail_batch_job(job_id, position, str(exc))
                return
            if index < len(job["items"]) - 1:
                time.sleep(job["interval_seconds"])
        self.db.complete_batch_job(job_id)

from __future__ import annotations

from types import SimpleNamespace
import re

from nimail_server.batch_service import BatchCreateService
from nimail_server.database import Database


class FakeAppleService:
    configured = True

    def __init__(self, fail_at: int | None = None):
        self.created: list[tuple[str, str]] = []
        self.fail_at = fail_at

    def create_alias(self, label: str, note: str) -> str:
        position = len(self.created) + 1
        if self.fail_at == position:
            raise RuntimeError("模拟 Apple 创建失败")
        self.created.append((label, note))
        return f"nimail-{position:03d}@icloud.com"


def payload(count: int) -> SimpleNamespace:
    return SimpleNamespace(
        count=count,
        label_prefix="购物",
        note="批量测试",
        interval_seconds=0,
        deactivate_after_seconds=1800,
        message_retention_seconds=86400,
        cdk_retention_seconds=86400,
        apple_action="deactivate",
    )


def make_service(tmp_path, apple):
    db = Database(tmp_path / "nimail-test.db")
    db.init()
    return db, BatchCreateService(db, apple)


def test_quantity_driven_batch_creates_numbered_aliases_and_cdks(tmp_path):
    apple = FakeAppleService()
    db, service = make_service(tmp_path, apple)

    created = service.start(payload(3))
    service.wait(created["id"])
    job = db.get_batch_job(created["id"])

    assert job["state"] == "completed"
    assert job["requested_count"] == 3
    assert job["success_count"] == 3
    labels = [item["label"] for item in job["items"]]
    assert len(set(labels)) == 3
    assert all(10 <= len(label) <= 18 and re.fullmatch(r"[A-Za-z2-9]+", label) for label in labels)
    assert all(not label.startswith("购物-") for label in labels)
    assert [item["address"] for item in job["items"]] == [
        "nimail-001@icloud.com", "nimail-002@icloud.com", "nimail-003@icloud.com"
    ]
    assert all(item["cdk"] for item in job["items"])
    assert len({item["cdk"] for item in job["items"]}) == 3
    assert all(db.mailbox_by_cdk(item["cdk"]) for item in job["items"])


def test_batch_stops_and_persists_failure_state(tmp_path):
    apple = FakeAppleService(fail_at=2)
    db, service = make_service(tmp_path, apple)

    created = service.start(payload(4))
    service.wait(created["id"])
    job = db.get_batch_job(created["id"])

    assert job["state"] == "failed"
    assert [item["state"] for item in job["items"]] == [
        "success", "failed", "cancelled", "cancelled"
    ]
    assert job["success_count"] == 1
    assert job["failed_count"] == 1
    assert job["completed_count"] == 4
    assert "模拟 Apple 创建失败" in job["error"]

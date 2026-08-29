from __future__ import annotations

from fastapi.testclient import TestClient

from nimail_server.app import create_app


class FakeAppleService:
    configured = True

    def __init__(self):
        self.labels: list[str] = []

    def create_alias(self, label: str, note: str = "") -> str:
        self.labels.append(label)
        return f"api-{len(self.labels):03d}@icloud.com"


def test_batch_api_accepts_a_quantity_and_returns_persisted_cdks(tmp_path, monkeypatch):
    app = create_app(data_dir=tmp_path / "data", start_workers=False)
    fake_apple = FakeAppleService()
    app.state.batch.apple_service = fake_apple
    monkeypatch.setattr("nimail_server.batch_service.time.sleep", lambda _seconds: None)

    with TestClient(app) as client:
        bootstrap_token = app.state.bootstrap_path.read_text(encoding="utf-8").strip()
        response = client.post("/api/bootstrap", json={
            "bootstrap_token": bootstrap_token,
            "username": "api-admin",
            "password": "Nimail-Api-Test-2026!",
        })
        assert response.status_code == 201

        login = client.post("/api/admin/login", json={
            "username": "api-admin", "password": "Nimail-Api-Test-2026!",
        })
        token = login.json()["token"]
        headers = {"Authorization": f"Bearer {token}"}

        started = client.post("/api/admin/apple/batch", headers=headers, json={
            "count": 4,
            "label_prefix": "服务",
            "note": "API 数量创建测试",
            "interval_seconds": 5,
            "deactivate_after_seconds": 1800,
            "message_retention_seconds": 86400,
            "cdk_retention_seconds": 86400,
            "apple_action": "deactivate",
        })
        assert started.status_code == 202
        job_id = started.json()["job"]["id"]
        app.state.batch.wait(job_id)

        result = client.get(f"/api/admin/apple/batch/{job_id}", headers=headers)
        assert result.status_code == 200
        job = result.json()["job"]
        assert job["state"] == "completed"
        assert job["requested_count"] == 4
        assert job["success_count"] == 4
        assert len(fake_apple.labels) == 4
        assert len(set(fake_apple.labels)) == 4
        assert all(not label.startswith("服务-") for label in fake_apple.labels)
        assert all(item["cdk"] and item["viewer_url"].endswith(item["cdk"])
                   for item in job["items"])

        configured = client.put("/api/admin/deployment", headers=headers, json={
            "domain": "mail.example.com",
        })
        assert configured.status_code == 200
        assert configured.json()["viewer_base_url"] == "https://mail.example.com"
        assert client.get("/api/admin/status", headers=headers).json()["deployment"]["mode"] == "server"
        remote_result = client.get(f"/api/admin/apple/batch/{job_id}", headers=headers).json()["job"]
        assert all(item["viewer_url"].startswith("https://mail.example.com/c/")
                   for item in remote_result["items"])

        mailboxes = client.get("/api/admin/mailboxes", headers=headers).json()["items"]
        assert len(mailboxes) == 4
        assert all(item["cdk"] for item in mailboxes)

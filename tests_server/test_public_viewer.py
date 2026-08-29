from __future__ import annotations

from fastapi.testclient import TestClient

from nimail_server.app import create_app


def test_public_viewer_returns_latest_first_and_exposes_compatibility_cards(tmp_path):
    app = create_app(data_dir=tmp_path / "data", start_workers=False)
    cdk = "LATEST-TEST-CDK"
    mailbox = app.state.db.create_mailbox(
        "latest@icloud.com", "latest", cdk, None, None, None, "keep"
    )
    app.state.db.add_message(
        mailbox["id"], 1, 1, "old", "old@example.com", "old",
        "2026-08-29T21:19:00+00:00", None, 0, "old body", "old body",
    )
    app.state.db.add_message(
        mailbox["id"], 1, 2, "new", "new@example.com", "new",
        "2026-08-30T06:06:00+08:00", "548977", 1, "new body 548977", "new body 548977",
    )

    with TestClient(app) as client:
        inbox = client.get(f"/api/public/c/{cdk}")
        assert inbox.status_code == 200
        assert [item["subject"] for item in inbox.json()["items"]] == ["new", "old"]

        page = client.get(f"/c/{cdk}")
        assert page.status_code == 200
        assert '<section id="nimail-compat-cards" hidden' in page.text
        assert '<article class="mail-card">' in page.text
        assert '<div class="meta">发件人：new@example.com</div>' in page.text
        assert '<pre class="body">new body 548977</pre>' in page.text
        assert page.text.index('发件人：new@example.com') < page.text.index(
            '发件人：old@example.com'
        )


def test_public_refresh_button_path_requests_immediate_imap_sync(tmp_path, monkeypatch):
    app = create_app(data_dir=tmp_path / "data", start_workers=False)
    cdk = "REFRESH-TEST-CDK"
    app.state.db.create_mailbox(
        "refresh@icloud.com", "refresh", cdk, None, None, None, "keep"
    )
    app.state.db.set_setting("imap_email", "main@icloud.com")
    app.state.db.set_setting("imap_app_password", "test-password", encrypted=True)
    calls = []
    monkeypatch.setattr(app.state.imap, "sync", lambda: calls.append(True) or {"added": 0})

    with TestClient(app) as client:
        response = client.get(f"/api/public/c/{cdk}?refresh=1")

    assert response.status_code == 200
    assert calls == [True]

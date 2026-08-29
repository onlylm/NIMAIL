from __future__ import annotations

import pytest

from nimail_desktop.api_client import ApiError, batch_txt_lines, validate_apple_cookie
from nimail_desktop.local_server import ensure_local_server, is_local_server_url, read_local_bootstrap_token


def test_only_loopback_urls_are_treated_as_local():
    assert is_local_server_url("http://127.0.0.1:8788")
    assert is_local_server_url("http://localhost:8788")
    assert not is_local_server_url("https://mail.example.com")


def test_ready_local_server_is_not_started(monkeypatch):
    monkeypatch.setattr("nimail_desktop.local_server.server_is_ready", lambda _url: True)
    monkeypatch.setattr(
        "nimail_desktop.local_server.find_server_executable",
        lambda: pytest.fail("服务已就绪时不应寻找或启动 EXE"),
    )
    assert ensure_local_server("http://127.0.0.1:8788") is False


def test_missing_local_server_executable_has_a_clear_error(monkeypatch):
    monkeypatch.setattr("nimail_desktop.local_server.server_is_ready", lambda _url: False)
    monkeypatch.setattr("nimail_desktop.local_server.find_server_executable", lambda: None)
    with pytest.raises(ApiError, match="NIMAIL-Server.exe"):
        ensure_local_server("http://127.0.0.1:8788")


def test_local_bootstrap_token_is_read_automatically(tmp_path, monkeypatch):
    token_file = tmp_path / "bootstrap-token.txt"
    token_file.write_text("x" * 64, encoding="utf-8")
    monkeypatch.setattr("nimail_desktop.local_server.bootstrap_token_candidates", lambda: (token_file,))
    assert read_local_bootstrap_token("http://127.0.0.1:8788") == "x" * 64


def test_remote_bootstrap_is_refused_even_when_a_token_file_exists(tmp_path, monkeypatch):
    token_file = tmp_path / "bootstrap-token.txt"
    token_file.write_text("x" * 64, encoding="utf-8")
    monkeypatch.setattr("nimail_desktop.local_server.bootstrap_token_candidates", lambda: (token_file,))
    with pytest.raises(ApiError, match="服务器本机"):
        read_local_bootstrap_token("https://mail.example.com")


def test_manual_cookie_requires_the_full_apple_session_cookie():
    with pytest.raises(ApiError, match="完整"):
        validate_apple_cookie("short")
    with pytest.raises(ApiError, match="X-APPLE-WEBAUTH-USER"):
        validate_apple_cookie("X-APPLE-WEBAUTH-TOKEN=abc; another=value")
    value = "X-APPLE-WEBAUTH-USER=123456; X-APPLE-WEBAUTH-TOKEN=secret"
    assert validate_apple_cookie("  " + value + "  ") == value


def test_batch_txt_export_uses_email_separator_and_viewer_url():
    job = {"items": [
        {"state": "success", "address": "one@icloud.com", "cdk": "AAAA-BBBB-CCCC-DDDD",
         "viewer_url": "https://mail.example.com/c/AAAA-BBBB-CCCC-DDDD"},
        {"state": "success", "address": "two@icloud.com", "cdk": "EEEE-FFFF-GGGG-HHHH"},
        {"state": "failed", "address": "", "cdk": ""},
    ]}
    assert batch_txt_lines(job, "http://127.0.0.1:8788") == [
        "one@icloud.com----https://mail.example.com/c/AAAA-BBBB-CCCC-DDDD",
        "two@icloud.com----http://127.0.0.1:8788/c/EEEE-FFFF-GGGG-HHHH",
    ]

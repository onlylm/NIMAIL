from __future__ import annotations

import os
import subprocess
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

from .api_client import ApiError, normalize_server_url


LOCAL_HOSTS = {"127.0.0.1", "localhost", "::1"}


def is_local_server_url(server_url: str) -> bool:
    parsed = urllib.parse.urlparse(normalize_server_url(server_url))
    return parsed.hostname in LOCAL_HOSTS


def server_is_ready(server_url: str) -> bool:
    try:
        request = urllib.request.Request(
            normalize_server_url(server_url) + "/healthz",
            headers={"Accept": "application/json"},
        )
        with urllib.request.urlopen(request, timeout=1.2) as response:
            return response.status == 200
    except (OSError, urllib.error.URLError, TimeoutError):
        return False


def find_server_executable() -> Path | None:
    executable_dir = Path(sys.executable).resolve().parent
    source_root = Path(__file__).resolve().parent.parent
    candidates = (
        executable_dir / "NIMAIL-Server.exe",
        executable_dir.parent / "dist-server" / "NIMAIL-Server.exe",
        source_root / "dist-server" / "NIMAIL-Server.exe",
    )
    return next((path for path in candidates if path.is_file()), None)


def bootstrap_token_candidates() -> tuple[Path, ...]:
    program_data = Path(os.environ.get("PROGRAMDATA", r"C:\ProgramData"))
    source_root = Path(__file__).resolve().parent.parent
    configured_data = os.environ.get("NIMAIL_SERVER_DATA", "").strip()
    candidates = []
    if configured_data:
        candidates.append(Path(configured_data) / "bootstrap-token.txt")
    candidates.extend((
        program_data / "NIMAIL" / "bootstrap-token.txt",
        source_root / "server_data" / "bootstrap-token.txt",
    ))
    return tuple(candidates)


def read_local_bootstrap_token(server_url: str) -> str:
    if not is_local_server_url(server_url):
        raise ApiError("为了服务器安全，请先在服务器本机打开管理端完成首次初始化")
    for path in bootstrap_token_candidates():
        try:
            token = path.read_text(encoding="utf-8").strip()
        except OSError:
            continue
        if len(token) >= 32:
            return token
    raise ApiError("无法自动读取本机初始化信息，请确认 NIMAIL-Server.exe 已正常启动")


def ensure_local_server(server_url: str, timeout_seconds: float = 12) -> bool:
    """本机服务不可用时后台启动它；返回 True 表示本次执行了启动。"""
    server_url = normalize_server_url(server_url)
    if not is_local_server_url(server_url) or server_is_ready(server_url):
        return False

    server_path = find_server_executable()
    if not server_path:
        raise ApiError("本机服务器未运行，且管理端目录中没有 NIMAIL-Server.exe")

    creation_flags = 0
    if os.name == "nt":
        creation_flags = subprocess.CREATE_NO_WINDOW | subprocess.CREATE_NEW_PROCESS_GROUP
    try:
        subprocess.Popen(
            [str(server_path)],
            cwd=str(server_path.parent),
            stdin=subprocess.DEVNULL,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            close_fds=True,
            creationflags=creation_flags,
        )
    except OSError as exc:
        raise ApiError(f"无法启动本机服务器：{exc}") from None

    deadline = time.monotonic() + timeout_seconds
    while time.monotonic() < deadline:
        if server_is_ready(server_url):
            return True
        time.sleep(0.25)
    raise ApiError("已经启动本机服务器，但 8788 端口未在规定时间内就绪")

from __future__ import annotations

import json
import re
import subprocess
import sys
import time
from pathlib import Path

from .config import PROJECT_ROOT


DOMAIN_RE = re.compile(
    r"^(?=.{4,253}$)(?:[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?\.)+[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?$"
)


def normalize_domain(value: str) -> str:
    domain = value.strip().lower()
    for prefix in ("https://", "http://"):
        if domain.startswith(prefix):
            domain = domain[len(prefix):]
    domain = domain.rstrip("/")
    if not DOMAIN_RE.fullmatch(domain):
        raise ValueError("请输入有效域名，例如 mail.example.com；不要包含协议、端口或路径")
    return domain


def load_deployment(data_dir: Path) -> dict:
    try:
        data = json.loads((data_dir / "deployment.json").read_text(encoding="utf-8-sig"))
    except (OSError, ValueError, TypeError):
        data = {}
    mode = "server" if data.get("mode") == "server" and data.get("domain") else "local"
    domain = str(data.get("domain") or "").strip().lower() if mode == "server" else ""
    return {
        "mode": mode,
        "domain": domain,
        "viewer_base_url": f"https://{domain}" if domain else "",
    }


def save_deployment(data_dir: Path, domain: str) -> dict:
    domain = normalize_domain(domain)
    data_dir.mkdir(parents=True, exist_ok=True)
    target = data_dir / "deployment.json"
    temporary = target.with_suffix(".json.tmp")
    temporary.write_text(
        json.dumps({"mode": "server", "domain": domain}, ensure_ascii=False),
        encoding="utf-8",
    )
    temporary.replace(target)
    return load_deployment(data_dir)


def caddyfile_text(domain: str) -> str:
    return f"""{{
\tadmin off
\tauto_https disable_redirects
}}

https://{domain} {{
\ttls {{
\t\tissuer acme {{
\t\t\tdisable_http_challenge
\t\t}}
\t}}
\tencode zstd gzip
\t@public path / /c /c/* /assets/* /api/public/c/*
\thandle @public {{
\t\treverse_proxy 127.0.0.1:8788
\t}}
\thandle {{
\t\trespond 404
\t}}
}}
"""


def _run(command: list[str], timeout: int = 20) -> subprocess.CompletedProcess:
    return subprocess.run(command, capture_output=True, text=True, timeout=timeout, check=False)


def _wait_service_stopped(sc_exe: str, timeout: float = 12.0) -> None:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        query = _run([sc_exe, "query", "NIMAIL-Caddy"], 5)
        output = (query.stdout + query.stderr).upper()
        if "STOPPED" in output or query.returncode != 0:
            return
        time.sleep(0.4)


def _caddy_service_bin_path(caddy_exe: Path, caddyfile: Path) -> str:
    return f'"{caddy_exe}" run --config "{caddyfile}" --adapter caddyfile'


def _create_caddy_service(sc_exe: str, caddy_exe: Path, caddyfile: Path) -> subprocess.CompletedProcess:
    return _run([
        sc_exe, "create", "NIMAIL-Caddy",
        "start=", "auto",
        "binPath=", _caddy_service_bin_path(caddy_exe, caddyfile),
        "DisplayName=", "NIMAIL HTTPS Gateway",
    ], 15)


def apply_server_domain(data_dir: Path, value: str) -> dict:
    """保存公网域名，并在一键安装环境中尽力更新内置 Caddy。"""
    deployment = save_deployment(data_dir, value)
    domain = deployment["domain"]
    app_dir = Path(sys.executable).resolve().parent if getattr(sys, "frozen", False) else PROJECT_ROOT
    caddy_exe = app_dir / "caddy.exe"
    caddyfile = app_dir / "Caddyfile"

    result = {**deployment, "gateway_status": "manual", "warning": ""}
    if not caddy_exe.is_file():
        result["warning"] = "域名已保存；未检测到内置 Caddy，请在现有 Nginx/网关中反向代理到 127.0.0.1:8788。"
        return result

    try:
        temporary = caddyfile.with_suffix(".tmp")
        temporary.write_text(caddyfile_text(domain), encoding="utf-8")
        validation = _run([str(caddy_exe), "validate", "--config", str(temporary), "--adapter", "caddyfile"])
        if validation.returncode != 0:
            temporary.unlink(missing_ok=True)
            result["warning"] = "域名已保存，但 HTTPS 配置校验失败。"
            return result
        temporary.replace(caddyfile)
    except (OSError, subprocess.SubprocessError) as exc:
        result["warning"] = f"域名已保存，但无法写入 HTTPS 配置：{exc}"
        return result

    if sys.platform != "win32":
        result["warning"] = "域名和 Caddyfile 已更新；请重启 Caddy 服务使其生效。"
        return result

    sc_exe = "sc.exe"
    query = _run([sc_exe, "query", "NIMAIL-Caddy"], 8)
    if query.returncode != 0:
        created = _create_caddy_service(sc_exe, caddy_exe, caddyfile)
        if created.returncode != 0:
            detail = (created.stdout + created.stderr).strip()
            result["warning"] = (
                "域名和 Caddyfile 已更新，但无法自动创建 HTTPS 服务。"
                "请以管理员身份重新打开匿邮管理端后再保存一次域名。"
            )
            if detail:
                result["gateway_detail"] = detail[-500:]
            return result
        _run([sc_exe, "description", "NIMAIL-Caddy", "NIMAIL public CDK gateway"], 8)
        _run([
            "netsh.exe", "advfirewall", "firewall", "add", "rule",
            "name=NIMAIL HTTPS", "dir=in", "action=allow", "protocol=TCP", "localport=443",
        ], 10)

    _run([sc_exe, "stop", "NIMAIL-Caddy"], 8)
    _wait_service_stopped(sc_exe)
    started = _run([sc_exe, "start", "NIMAIL-Caddy"], 15)
    if started.returncode == 0:
        result["gateway_status"] = "running"
    else:
        detail = (started.stdout + started.stderr).strip()
        result["warning"] = "域名已更新，但 HTTPS 网关启动失败；请检查 443 端口是否被占用或未在云安全组开放。"
        if detail:
            result["gateway_detail"] = detail[-500:]
    return result

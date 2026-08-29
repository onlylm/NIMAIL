from __future__ import annotations

import subprocess
from pathlib import Path


def server_task_create_command(server_exe: Path) -> list[str]:
    return [
        "schtasks.exe", "/Create",
        "/TN", "NIMAIL-Server",
        "/SC", "ONSTART",
        "/RU", "SYSTEM",
        "/RL", "HIGHEST",
        "/TR", str(server_exe),
        "/F",
    ]


def _run(command: list[str], timeout: int = 30) -> subprocess.CompletedProcess:
    return subprocess.run(command, capture_output=True, text=True, timeout=timeout, check=False)


def install_server_task(server_exe: Path) -> tuple[bool, str]:
    """Create and start the boot task without shell-level quoting."""
    _run(["schtasks.exe", "/End", "/TN", "NIMAIL-Server"], 10)
    _run(["schtasks.exe", "/Delete", "/TN", "NIMAIL-Server", "/F"], 10)
    _run(["schtasks.exe", "/End", "/TN", "NIMAIL Server"], 10)
    _run(["schtasks.exe", "/Delete", "/TN", "NIMAIL Server", "/F"], 10)

    created = _run(server_task_create_command(server_exe), 30)
    if created.returncode != 0:
        detail = (created.stdout + created.stderr).strip()
        return False, detail or f"schtasks create exited with {created.returncode}"

    started = _run(["schtasks.exe", "/Run", "/TN", "NIMAIL-Server"], 20)
    if started.returncode != 0:
        detail = (started.stdout + started.stderr).strip()
        return False, detail or f"schtasks run exited with {started.returncode}"
    return True, "NIMAIL-Server task created and started"

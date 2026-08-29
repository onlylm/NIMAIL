from __future__ import annotations

import base64
import json
from pathlib import Path

from emailhub.secrets_store import protect, unprotect

from .config import DATA_DIR


PATH = DATA_DIR / "admin-session.dat"


def load() -> dict:
    if not PATH.exists():
        return {}
    try:
        encrypted = base64.b64decode(PATH.read_bytes(), validate=True)
        return json.loads(unprotect(encrypted).decode("utf-8"))
    except Exception:
        return {}


def save(server_url: str, username: str, token: str) -> None:
    payload = json.dumps(
        {"server_url": server_url, "username": username, "token": token}, ensure_ascii=False
    ).encode("utf-8")
    temporary = PATH.with_suffix(".tmp")
    temporary.write_bytes(base64.b64encode(protect(payload)))
    temporary.replace(PATH)


def clear() -> None:
    if PATH.exists():
        PATH.unlink()

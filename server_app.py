from __future__ import annotations

import json
import sys
from pathlib import Path

import uvicorn

from nimail_server.app import app
from nimail_server.config import DATA_DIR
from nimail_server.deployment import apply_server_domain
from nimail_server.windows_setup import install_server_task


def main() -> int:
    if len(sys.argv) >= 2 and sys.argv[1] == "--install-server-task":
        ok, detail = install_server_task(Path(sys.executable).resolve())
        print(json.dumps({"ok": ok, "detail": detail}, ensure_ascii=False))
        return 0 if ok else 2

    if len(sys.argv) >= 3 and sys.argv[1] == "--install-caddy":
        result = apply_server_domain(DATA_DIR, sys.argv[2])
        print(json.dumps(result, ensure_ascii=False))
        return 0 if result.get("gateway_status") == "running" and not result.get("warning") else 3

    uvicorn.run(app, host="127.0.0.1", port=8788, access_log=False,
                proxy_headers=True, forwarded_allow_ips="127.0.0.1")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

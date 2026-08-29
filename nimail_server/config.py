from __future__ import annotations

import os
import sys
from pathlib import Path


FROZEN = bool(getattr(sys, "frozen", False))
PROJECT_ROOT = Path(getattr(sys, "_MEIPASS", Path(__file__).resolve().parent.parent))
DEFAULT_DATA_DIR = (
    Path(os.environ.get("PROGRAMDATA", Path.home())) / "NIMAIL"
    if FROZEN
    else PROJECT_ROOT / "server_data"
)
DATA_DIR = Path(os.environ.get("NIMAIL_SERVER_DATA", DEFAULT_DATA_DIR)).resolve()
WEB_DIR = PROJECT_ROOT / "server_web"


def ensure_data_dir(path: Path = DATA_DIR) -> Path:
    path.mkdir(parents=True, exist_ok=True)
    return path

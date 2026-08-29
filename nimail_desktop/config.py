from __future__ import annotations

import os
import sys
from pathlib import Path


FROZEN = bool(getattr(sys, "frozen", False))
RESOURCE_ROOT = Path(getattr(sys, "_MEIPASS", Path(__file__).resolve().parent.parent))
ASSET_DIR = RESOURCE_ROOT / "desktop_assets"
DEFAULT_DATA_DIR = Path(os.environ.get("LOCALAPPDATA", Path.home())) / "NIMAIL" / "Admin"
DATA_DIR = Path(os.environ.get("NIMAIL_ADMIN_DATA", DEFAULT_DATA_DIR)).resolve()
DATA_DIR.mkdir(parents=True, exist_ok=True)

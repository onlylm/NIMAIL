from __future__ import annotations

import sys

from PySide6.QtGui import QIcon
from PySide6.QtWidgets import QApplication

from nimail_desktop.config import ASSET_DIR
from nimail_desktop.main_window import MainWindow


if __name__ == "__main__":
    app = QApplication(sys.argv)
    app.setApplicationName("匿邮管理端")
    app.setOrganizationName("NIMAIL")
    app.setStyle("Fusion")
    icon = QIcon(str(ASSET_DIR / "logo.png"))
    if not icon.isNull(): app.setWindowIcon(icon)
    window = MainWindow()
    window.show()
    raise SystemExit(app.exec())

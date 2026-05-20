from __future__ import annotations

import sys
from pathlib import Path

from PySide6.QtWidgets import QApplication

from .gui.main_window import MainWindow
from .logging_config import setup_logging


def main() -> int:
    setup_logging()
    app = QApplication(sys.argv)
    app.setApplicationName("魔王心理学模板")
    window = MainWindow()
    window.resize(980, 760)
    window.show()
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())


"""Start the IDE."""
import sys

from PySide6.QtWidgets import QApplication


def run_ide(files=()):
    app = QApplication.instance() or QApplication(sys.argv[:1])
    app.setApplicationName("OpenBASIC")
    app.setOrganizationName("OpenBASIC")
    from .mainwindow import MainWindow
    from . import icons
    app.setWindowIcon(icons.app_icon())
    w = MainWindow(files)
    w.show()
    return app.exec()

"""Run a BASIC program with the Qt runtime (used by the IDE and standalone apps)."""
import os
import sys
import traceback

from ..errors import BasicError, BasicSyntaxError, EndProgram, StopRequested
from ..interp import Interpreter


class RunResult:
    def __init__(self, status, error=None, line=None):
        self.status = status  # 'ended', 'stopped', 'error', 'syntax'
        self.error = error
        self.line = line


def run_program(app, source, filename, debug_ui=None, debugger=None, argv="", host_ready=None):
    from .qthost import QtHost
    name = os.path.basename(filename) if filename else "untitled.bas"
    host = QtHost(app, name, debug_ui=debug_ui)
    try:
        interp = Interpreter(source, host, filename, debugger=debugger, argv=argv)
    except BasicSyntaxError as e:
        host.shutdown()
        return RunResult("syntax", e.msg, e.line), host
    except BasicError as e:
        host.shutdown()
        return RunResult("syntax", e.msg, e.line), host
    host.interp = interp
    if host_ready:
        host_ready(host, interp)
    result = RunResult("ended")
    try:
        interp.run()
    except StopRequested:
        result = RunResult("stopped", line=interp.current_line)
    except BasicError as e:
        result = RunResult("error", e.msg, e.line or interp.current_line)
    except EndProgram:
        pass
    except Exception as e:  # a bug in OpenBASIC itself; report it rather than crash
        tb = traceback.format_exc()
        sys.stderr.write(tb)
        result = RunResult("error", f"Internal error: {e.__class__.__name__}: {e}", interp.current_line)
    finally:
        host.shutdown()
    return result, host


def main_standalone(path=None, source=None, argv=""):
    """Entry point for running a program outside the IDE."""
    from PySide6.QtWidgets import QApplication, QMessageBox
    app = QApplication.instance() or QApplication(sys.argv)
    app.setQuitOnLastWindowClosed(False)
    if source is None:
        with open(path, "r", encoding="utf-8", errors="replace") as f:
            source = f.read()
    result, host = run_program(app, source, path, argv=argv)
    if result.status in ("error", "syntax"):
        where = f" on line {result.line}" if result.line else ""
        QMessageBox.critical(None, "Program error", f"{result.error}{where}")
        return 1
    if host.console is not None and host.console.isVisible():
        host.console.setWindowTitle(host.console.windowTitle() + " (finished)")
        app.setQuitOnLastWindowClosed(True)
        app.exec()
    return 0

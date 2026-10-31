"""Drive a BASIC program headlessly: run scripted actions on timers, take screenshots."""
import os, sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
from PySide6.QtCore import QTimer, QPoint, Qt
from PySide6.QtWidgets import QApplication
from PySide6.QtTest import QTest
from openbasic.runtime.runner import run_program

app = QApplication.instance() or QApplication(sys.argv)
state = {}

def run(path, steps, timeout_ms=20000):
    """steps: list of (delay_ms, fn(host)) executed in order."""
    src = open(path, encoding="utf-8", errors="replace").read()
    def ready(host, interp):
        state["host"] = host
        t = 0
        for delay, fn in steps:
            t += delay
            QTimer.singleShot(t, lambda fn=fn: _safe(fn, host))
        QTimer.singleShot(timeout_ms, lambda: host.request_stop())
    return run_program(app, src, path, host_ready=ready)

def _safe(fn, host):
    try:
        fn(host)
    except Exception as e:
        import traceback; traceback.print_exc()
        host.request_stop()

def shot(widget, name):
    p = os.path.join(os.environ.get("SHOTS", "/tmp/claude-0/shots"), name)
    widget.grab().save(p)
    print("saved", p)

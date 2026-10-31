"""Run one BASIC program with an automatic user (dismisses dialogs, answers INPUT with 5) and print a JSON result line. Used by run_corpus.py."""
import json, os, sys, time
os.environ["QT_QPA_PLATFORM"] = "offscreen"
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from PySide6.QtCore import QTimer, Qt
from PySide6.QtWidgets import QApplication, QMessageBox, QDialog, QInputDialog, QFileDialog
from PySide6.QtTest import QTest
from openbasic.runtime.runner import run_program

path, secs = sys.argv[1], float(sys.argv[2]) if len(sys.argv) > 2 else 3
app = QApplication(sys.argv[:1])
data = open(path, "rb").read()
try: src = data.decode("utf-8")
except UnicodeDecodeError: src = data.decode("cp1252")
info = {"dialogs": 0, "inputs": 0}

def auto(host):
    w = QApplication.activeModalWidget()
    if w is not None:
        info["dialogs"] += 1
        if isinstance(w, QMessageBox):
            b = w.defaultButton() or (w.buttons()[0] if w.buttons() else None)
            b.click() if b else w.reject()
        elif isinstance(w, QInputDialog):
            w.setTextValue("5"); w.accept()
        else:
            w.reject()
    con = host.console
    if con is not None and con.edit.input_start is not None:
        info["inputs"] += 1
        QTest.keyClicks(con.edit, "5" if info["inputs"] < 40 else "q")
        QTest.keyClick(con.edit, Qt.Key_Return)

def ready(host, interp):
    t = QTimer(); t.timeout.connect(lambda: auto(host)); t.start(150)
    host._autotimer = t
    QTimer.singleShot(int(secs * 1000) - 500, lambda: snap(host))
    QTimer.singleShot(int(secs * 1000), host.request_stop)

def snap(host):
    d = os.environ.get("SHOT_DIR")
    if not d:
        return
    from PySide6.QtGui import QImage, QPainter, QColor
    wins = [w for w in list(host.windows.values()) if w.isVisible()]
    if host.console is not None and host.console.isVisible():
        wins.append(host.console)
    if not wins:
        return
    pms = [w.grab() for w in wins]
    W = sum(p.width() for p in pms) + 8 * (len(pms) - 1); H = max(p.height() for p in pms)
    img = QImage(max(W, 1), max(H, 1), QImage.Format_RGB32); img.fill(QColor(80, 80, 80))
    pt = QPainter(img); x = 0
    for pm in pms:
        pt.drawPixmap(x, 0, pm); x += pm.width() + 8
    pt.end()
    img.save(os.path.join(d, os.path.relpath(path).replace("/", "_") + ".png"))

start = time.time()
result, host = run_program(app, src, os.path.abspath(path), host_ready=ready)
lines = src.replace("\r\n", "\n").replace("\r", "\n").split("\n")
out = {"file": os.path.relpath(path), "status": result.status, "error": result.error, "line": result.line,
       "src": lines[result.line - 1].strip()[:120] if result.line and result.line <= len(lines) else "",
       "secs": round(time.time() - start, 1), **info,
       "console": (host.console.edit.toPlainText()[-300:] if host.console else "")}
print("RESULT " + json.dumps(out))

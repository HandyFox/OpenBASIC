"""Run real programs through the Qt runtime (offscreen) with scripted clicks."""
import os
import shutil
import sys

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from harness import QApplication, QPoint, QTest, run  # noqa: E402
from PySide6.QtWidgets import QMessageBox  # noqa: E402

SAMPLES = os.path.join(os.path.dirname(os.path.abspath(__file__)), "samples")
EXAMPLES = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "openbasic", "examples")


@pytest.fixture
def workdir(tmp_path):
    for f in os.listdir(SAMPLES):
        src = os.path.join(SAMPLES, f)
        (shutil.copytree if os.path.isdir(src) else shutil.copy)(src, tmp_path / f)
    return tmp_path


def test_target_sprites_follow_mouse(workdir):
    seen = {}

    def move(h):
        v = h.windows["#main"].controls["#main.graph"].widget
        QTest.mouseMove(v, QPoint(300, 250))

    def check(h):
        v = h.windows["#main"].controls["#main.graph"].widget
        seen["square"] = (v.sprites["square"].x, v.sprites["square"].y)
        seen["target"] = (v.sprites["target"].x, v.sprites["target"].y)
        h.windows["#main"].close()

    r, _ = run(str(workdir / "Target.bas"), [(300, move), (300, check)])
    assert r.status == "ended", r.error
    assert seen["square"] == (280, 246)
    assert seen["target"] in {(415, 147), (185, 294), (613, 294), (406, 295), (188, 472), (626, 479)}


def test_ponderosa_full_flow(workdir):
    QApplication.clipboard().setText("package:com.android.chrome\npackage:org.mozilla.firefox\n")
    log = {}

    def answer_no(h):
        QApplication.activeModalWidget().button(QMessageBox.No).click()

    def click(key):
        return lambda h: h.controls[key].widget.click()

    def typ(key, text):
        return lambda h: h.controls[key].widget.setText(text)

    def read_info(h):
        log["info"] = h.controls["#main.info"].widget.text()
        h.windows["#main"].close()

    steps = [
        (400, click("#main.button9")), (300, answer_no),
        (400, typ("#results.search", "fox")), (100, click("#results.button21")),
        (300, click("#results.bmpbutton2")), (200, click("#results.done")), (300, answer_no),
        (500, read_info),
    ]
    old = os.getcwd()
    os.chdir(workdir)  # RUN commands start here; nothing else depends on it
    try:
        r, _ = run(str(workdir / "Ponderosa2.bas"), steps)
    finally:
        os.chdir(old)
    assert r.status == "ended", r.error
    profile = (workdir / "profile.json").read_text()
    assert '"org.mozilla.firefox"' in profile
    assert (workdir / "PHONELOG.txt").exists()
    assert "Ponderosa" in log["info"]


@pytest.mark.parametrize("name,handle", [("2_GUI_Form.bas", "#main"), ("3_Turtle_Graphics.bas", "#g"),
                                         ("4_Sprite_Bounce.bas", "#w"), ("5_Notepad.bas", "#pad")])
def test_examples_run(name, handle):
    r, _ = run(os.path.join(EXAMPLES, name), [(600, lambda h: h.windows[handle].close())])
    assert r.status == "ended", r.error


def test_runtime_error_reports_line():
    import tempfile
    p = os.path.join(tempfile.mkdtemp(), "bad.bas")
    open(p, "w").write("nomainwin\nx = 1\ny = x / 0\n")
    r, _ = run(p, [])
    assert r.status == "error" and r.line == 3 and "Division by zero" in r.error

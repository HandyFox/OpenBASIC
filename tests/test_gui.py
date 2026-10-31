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


def test_old_style_window_input(tmp_path):
    """Liberty BASIC 1.x style: query then INPUT #handle, and INPUT #window as an event wait."""
    p = tmp_path / "old.bas"
    p.write_text('''nomainwin
textbox #w.tb, 10, 10, 100, 25
button #w.b, "Go", [go], UL, 10, 50
open "Old style" for window as #w
h$ = "#w"
print #h$.tb, "hello there"
print #w.tb, "!contents?"
input #w.tb, got$
open "out.txt" for output as #f
print #f, got$
[loop]
input #w, r$
goto [loop]
[go]
print #f, "clicked"
close #f
close #w
end
''')
    r, _ = run(str(p), [(300, lambda h: h.controls["#w.b"].widget.click())])
    assert r.status == "ended", r.error
    assert (tmp_path / "out.txt").read_text().split() == ["hello", "there", "clicked"]


def test_graphics_segments_and_stacked_text(tmp_path):
    """SEGMENT.BAS style: text lines stack, delsegment + redraw remove drawings."""
    p = tmp_path / "seg.bas"
    p.write_text('''nomainwin
open "seg" for graphics as #g
print #g, "place 10 25"
print #g, "\\ONE"
print #g, "flush"
print #g, "\\TWO"
print #g, "flush"
print #g, "posxy x y"
print #g, "delsegment 2"
print #g, "redraw"
open "out.txt" for output as #f
print #f, x; " "; y
close #f
wait
''')
    snap = {}

    def check(h):
        v = h.windows["#g"].view
        img = v.img
        # ONE's row has dark pixels; TWO's row was deleted
        def dark_in_row(y0, y1):
            return any(img.pixelColor(x, y).lightness() < 100 for y in range(y0, y1) for x in range(10, 80))
        snap["one"] = dark_in_row(10, 26)
        snap["two"] = dark_in_row(30, 44)
        h.windows["#g"].close()

    r, _ = run(str(p), [(400, check)])
    assert r.status == "ended", r.error
    x, y = (tmp_path / "out.txt").read_text().split()
    assert x == "10" and int(y) > 40  # the pen moved down two lines
    assert snap["one"] and not snap["two"]


def test_corner_anchored_buttons_stay_inside(tmp_path):
    """CALC2.BAS style: LL buttons with a negative offset keep their spacing inside the window."""
    p = tmp_path / "calc.bas"
    p.write_text('''nomainwin
button #c, " 0 ", [x], LL, 5, -12
button #c, " 1 ", [x], LL, 5, 16
WindowWidth = 150 : WindowHeight = 280
open "Calc" for graphics_nsb_nf as #c
wait
[x] wait
''')
    geo = {}

    def check(h):
        w = h.windows["#c"]
        b0, b1 = [c.widget.geometry() for c in w.controls.values()]
        geo.update(b0=b0, b1=b1, h=w.area.height())
        w.close()

    r, _ = run(str(p), [(300, check)])
    assert r.status == "ended", r.error
    assert geo["b0"].bottom() < geo["h"]
    assert geo["b0"].top() - geo["b1"].top() == 28

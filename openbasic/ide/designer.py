"""FreeForm-style GUI designer: drag controls onto a window, then generate BASIC code."""
import os
import re

from PySide6.QtCore import QMimeData, QPoint, QRect, QSize, Qt, Signal
from PySide6.QtGui import QAction, QColor, QDrag, QFont, QKeySequence, QPainter, QPen, QPixmap
from PySide6.QtWidgets import (QApplication, QCheckBox, QComboBox, QFileDialog, QFormLayout, QFrame, QGroupBox,
                               QHBoxLayout, QLabel, QLineEdit, QListWidget, QListWidgetItem, QMainWindow,
                               QMessageBox, QPlainTextEdit, QPushButton, QRadioButton, QScrollArea, QSpinBox,
                               QSplitter, QToolBar, QVBoxLayout, QWidget)

from ..parser import parse
from ..runtime.style import parse_font, program_palette

FRAME_W, FRAME_H = 8, 27
GRID = 5

TYPES = [
    ("button", "Button", 100, 25),
    ("bmpbutton", "BMP Button", 40, 40),
    ("textbox", "TextBox", 150, 25),
    ("texteditor", "TextEditor", 220, 120),
    ("statictext", "StaticText", 120, 20),
    ("groupbox", "GroupBox", 200, 120),
    ("listbox", "ListBox", 150, 100),
    ("combobox", "ComboBox", 150, 25),
    ("checkbox", "CheckBox", 120, 20),
    ("radiobutton", "RadioButton", 120, 20),
    ("graphicbox", "GraphicBox", 200, 150),
]
TYPE_INFO = {t: (label, w, h) for t, label, w, h in TYPES}
WINDOW_TYPES = ["window", "window_nf", "dialog", "dialog_modal", "dialog_nf", "dialog_nf_modal", "graphics",
                "graphics_nsb", "graphics_nf_nsb"]
MIME = "application/x-openbasic-control"


def snap(v):
    return int(round(v / GRID) * GRID)


class Item(QWidget):
    """One control on the design surface."""

    def __init__(self, surface, spec):
        super().__init__(surface)
        self.surface = surface
        self.spec = spec
        self.preview = None
        self.selected = False
        self.drag = None
        self.setMouseTracking(True)
        self.setFocusPolicy(Qt.ClickFocus)
        self.rebuild()

    def rebuild(self):
        if self.preview is not None:
            self.preview.deleteLater()
        s = self.spec
        t = s["type"]
        text = s.get("text", "")
        if t == "button":
            w = QPushButton(text, self)
        elif t == "bmpbutton":
            w = QPushButton(self)
            pm = QPixmap(s.get("file_real", ""))
            if not pm.isNull():
                from PySide6.QtGui import QIcon
                w.setIcon(QIcon(pm))
                w.setIconSize(pm.size())
            else:
                w.setText("BMP")
        elif t == "textbox":
            w = QLineEdit(self)
            w.setPlaceholderText(s["name"])
        elif t == "texteditor":
            w = QPlainTextEdit(self)
            w.setPlaceholderText(s["name"])
        elif t == "statictext":
            w = QLabel(text, self)
            w.setWordWrap(s["h"] >= 30)
            w.setAlignment(Qt.AlignLeft | Qt.AlignTop)
        elif t == "groupbox":
            w = QGroupBox(text, self)
        elif t == "listbox":
            w = QListWidget(self)
            w.addItems([f"{s.get('array', 'items$')}(…)"])
        elif t == "combobox":
            w = QComboBox(self)
            w.addItem(f"{s.get('array', 'items$')}(…)")
        elif t == "checkbox":
            w = QCheckBox(text, self)
        elif t == "radiobutton":
            w = QRadioButton(text, self)
        else:
            w = QLabel(self)
            w.setStyleSheet("background: white; border: 1px solid #888;")
            w.setAlignment(Qt.AlignCenter)
            w.setText(f"#{s['name']}")
        w.setAttribute(Qt.WA_TransparentForMouseEvents)
        w.setFocusPolicy(Qt.NoFocus)
        if self.surface.form_font is not None:
            w.setFont(self.surface.form_font)
        self.preview = w
        w.show()
        self.place()

    def place(self):
        s = self.spec
        self.setGeometry(s["x"], s["y"], s["w"], s["h"])
        self.preview.setGeometry(0, 0, s["w"], s["h"])
        if s["type"] == "groupbox":
            self.lower()

    def paintEvent(self, ev):
        if not self.selected:
            return
        p = QPainter(self)
        p.setPen(QPen(QColor("#2f6fdf"), 1, Qt.DashLine))
        p.drawRect(0, 0, self.width() - 1, self.height() - 1)
        p.setPen(Qt.NoPen)
        p.setBrush(QColor("#2f6fdf"))
        for x, y in self._handles():
            p.drawRect(x - 3, y - 3, 6, 6)
        p.end()

    def _handles(self):
        w, h = self.width() - 1, self.height() - 1
        return [(0, 0), (w // 2, 0), (w, 0), (0, h // 2), (w, h // 2), (0, h), (w // 2, h), (w, h)]

    def _edge(self, pos):
        x, y = pos.x(), pos.y()
        w, h = self.width(), self.height()
        m = 6
        left, right = x <= m, x >= w - m
        top, bottom = y <= m, y >= h - m
        return ("t" if top else "b" if bottom else "") + ("l" if left else "r" if right else "")

    def _cursor_for(self, edge):
        return {"tl": Qt.SizeFDiagCursor, "br": Qt.SizeFDiagCursor, "tr": Qt.SizeBDiagCursor,
                "bl": Qt.SizeBDiagCursor, "t": Qt.SizeVerCursor, "b": Qt.SizeVerCursor,
                "l": Qt.SizeHorCursor, "r": Qt.SizeHorCursor}.get(edge, Qt.SizeAllCursor)

    def mousePressEvent(self, ev):
        if ev.button() != Qt.LeftButton:
            return
        self.surface.select(self)
        self.setFocus()
        edge = self._edge(ev.position().toPoint()) if self.selected else ""
        self.drag = (edge, ev.globalPosition().toPoint(), dict(self.spec))

    def mouseMoveEvent(self, ev):
        if self.drag is None:
            self.setCursor(self._cursor_for(self._edge(ev.position().toPoint()) if self.selected else ""))
            return
        edge, start, orig = self.drag
        d = ev.globalPosition().toPoint() - start
        s = self.spec
        if not edge:
            s["x"] = max(0, snap(orig["x"] + d.x()))
            s["y"] = max(0, snap(orig["y"] + d.y()))
        else:
            if "l" in edge:
                nx = snap(orig["x"] + d.x())
                s["w"] = max(10, orig["w"] + orig["x"] - nx)
                s["x"] = orig["x"] + orig["w"] - s["w"]
            if "r" in edge:
                s["w"] = max(10, snap(orig["w"] + d.x()))
            if "t" in edge:
                ny = snap(orig["y"] + d.y())
                s["h"] = max(10, orig["h"] + orig["y"] - ny)
                s["y"] = orig["y"] + orig["h"] - s["h"]
            if "b" in edge:
                s["h"] = max(10, snap(orig["h"] + d.y()))
        self.place()
        self.surface.changed.emit()

    def mouseReleaseEvent(self, ev):
        self.drag = None

    def mouseDoubleClickEvent(self, ev):
        self.surface.edit_requested.emit(self)

    def keyPressEvent(self, ev):
        s = self.spec
        step = GRID if not ev.modifiers() & Qt.ShiftModifier else 1
        k = ev.key()
        if k == Qt.Key_Delete or k == Qt.Key_Backspace:
            self.surface.remove(self)
            return
        if k in (Qt.Key_Left, Qt.Key_Right, Qt.Key_Up, Qt.Key_Down):
            if ev.modifiers() & Qt.ControlModifier:
                if k == Qt.Key_Left:
                    s["w"] = max(10, s["w"] - step)
                elif k == Qt.Key_Right:
                    s["w"] += step
                elif k == Qt.Key_Up:
                    s["h"] = max(10, s["h"] - step)
                else:
                    s["h"] += step
            else:
                if k == Qt.Key_Left:
                    s["x"] = max(0, s["x"] - step)
                elif k == Qt.Key_Right:
                    s["x"] += step
                elif k == Qt.Key_Up:
                    s["y"] = max(0, s["y"] - step)
                else:
                    s["y"] += step
            self.place()
            self.surface.changed.emit()
            return
        super().keyPressEvent(ev)


class Surface(QWidget):
    """The window's client area."""
    selected_changed = Signal(object)
    changed = Signal()
    edit_requested = Signal(object)

    def __init__(self):
        super().__init__()
        self.items = []
        self.current = None
        self.show_grid = True
        self.form_font = None
        self.setAcceptDrops(True)
        self.setAutoFillBackground(True)
        self.setPalette(program_palette())
        self.setFocusPolicy(Qt.ClickFocus)

    def paintEvent(self, ev):
        p = QPainter(self)
        p.fillRect(self.rect(), QColor("#f0f0f0"))
        if self.show_grid:
            p.setPen(QColor("#c8c8c8"))
            for x in range(0, self.width(), GRID * 4):
                for y in range(0, self.height(), GRID * 4):
                    p.drawPoint(x, y)
        p.end()

    def add(self, spec, select=True):
        it = Item(self, spec)
        it.show()
        self.items.append(it)
        if spec["type"] == "groupbox":
            it.lower()
        if select:
            self.select(it)
        self.changed.emit()
        return it

    def remove(self, it):
        if it in self.items:
            self.items.remove(it)
            it.deleteLater()
            if self.current is it:
                self.current = None
                self.selected_changed.emit(None)
            self.changed.emit()

    def clear(self):
        for it in list(self.items):
            it.deleteLater()
        self.items = []
        self.current = None
        self.selected_changed.emit(None)

    def select(self, it):
        if self.current is it:
            return
        if self.current is not None:
            self.current.selected = False
            self.current.update()
        self.current = it
        if it is not None:
            it.selected = True
            it.raise_() if it.spec["type"] != "groupbox" else None
            it.update()
        self.selected_changed.emit(it)

    def mousePressEvent(self, ev):
        self.select(None)
        self.setFocus()

    def dragEnterEvent(self, ev):
        if ev.mimeData().hasFormat(MIME):
            ev.acceptProposedAction()

    def dragMoveEvent(self, ev):
        ev.acceptProposedAction()

    def dropEvent(self, ev):
        t = bytes(ev.mimeData().data(MIME)).decode()
        pos = ev.position().toPoint()
        self.designer.add_control(t, snap(pos.x()), snap(pos.y()))
        ev.acceptProposedAction()


class Palette(QListWidget):
    def __init__(self, designer):
        super().__init__()
        self.designer = designer
        self.setDragEnabled(True)
        for t, label, _, _ in TYPES:
            it = QListWidgetItem(label)
            it.setData(Qt.UserRole, t)
            it.setToolTip("Drag onto the window, or double-click to add")
            self.addItem(it)
        self.itemDoubleClicked.connect(lambda it: designer.add_control(it.data(Qt.UserRole)))

    def startDrag(self, actions):
        it = self.currentItem()
        if not it:
            return
        md = QMimeData()
        md.setData(MIME, it.data(Qt.UserRole).encode())
        d = QDrag(self)
        d.setMimeData(md)
        d.exec(Qt.CopyAction)


class FormFrame(QWidget):
    """Draws a simple title bar above the surface so it looks like a window."""

    def __init__(self, surface):
        super().__init__()
        self.surface = surface
        self.title = "Untitled Window"
        surface.setParent(self)

    def set_client_size(self, w, h):
        self.surface.setGeometry(8, 30, w, h)
        self.setFixedSize(w + 16, h + 38)
        self.update()

    def paintEvent(self, ev):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        p.setPen(QColor("#9aa0a6"))
        p.setBrush(QColor("#dde3ea"))
        p.drawRoundedRect(QRect(0, 0, self.width() - 1, self.height() - 1), 6, 6)
        p.setPen(QColor("#1f2328"))
        f = p.font()
        f.setBold(True)
        p.setFont(f)
        p.drawText(QRect(12, 0, self.width() - 80, 30), Qt.AlignVCenter | Qt.AlignLeft, self.title)
        for i, c in enumerate(("#f5c518", "#22a559", "#e5484d")):
            p.setPen(Qt.NoPen)
            p.setBrush(QColor(c))
            p.drawEllipse(self.width() - 22 - i * 18, 10, 11, 11)
        p.end()


class DesignerWindow(QMainWindow):
    def __init__(self, ide):
        super().__init__(ide)
        self.ide = ide
        self.setWindowTitle("FreeForm GUI Designer — OpenBASIC")
        self.setWindowFlag(Qt.Window, True)
        self.resize(1150, 720)
        self.win = {"title": "Untitled Window", "handle": "main", "type": "window", "w": 550, "h": 410,
                    "font": "ms_sans_serif 10", "center": True}
        self.counter = {}

        self.surface = Surface()
        self.surface.designer = self
        self.frame = FormFrame(self.surface)
        holder = QWidget()
        hl = QVBoxLayout(holder)
        hl.addWidget(self.frame, 0, Qt.AlignLeft | Qt.AlignTop)
        hl.addStretch()
        scroll = QScrollArea()
        scroll.setWidget(holder)
        scroll.setWidgetResizable(True)

        self.palette_ = Palette(self)
        left = QWidget()
        ll = QVBoxLayout(left)
        ll.setContentsMargins(4, 4, 4, 4)
        ll.addWidget(QLabel("<b>Controls</b>"))
        ll.addWidget(self.palette_)
        ll.addWidget(QLabel("<small>Drag a control onto the window.<br>Arrows move, Ctrl+arrows resize,<br>"
                            "Delete removes.</small>"))

        self.props = QWidget()
        self.form = QFormLayout(self.props)
        right = QScrollArea()
        right.setWidget(self.props)
        right.setWidgetResizable(True)
        right.setMinimumWidth(300)

        split = QSplitter()
        split.addWidget(left)
        split.addWidget(scroll)
        split.addWidget(right)
        split.setStretchFactor(1, 1)
        split.setSizes([170, 680, 300])
        self.setCentralWidget(split)

        tb = QToolBar()
        tb.setMovable(False)
        self.addToolBar(tb)
        for text, slot in (("Insert Code into Editor", lambda: self.generate(False)),
                           ("Code in New Tab", lambda: self.generate(True)),
                           ("Copy Code", self.copy_code),
                           ("Import from Selection", self.import_from_editor),
                           ("Delete Control", self.delete_selected),
                           ("Duplicate", self.duplicate),
                           ("New Form", self.new_form)):
            a = QAction(text, self)
            a.triggered.connect(slot)
            tb.addAction(a)
        self.stubs = QCheckBox("Add handler stubs")
        self.stubs.setChecked(True)
        tb.addSeparator()
        tb.addWidget(self.stubs)
        self.grid_cb = QCheckBox("Grid")
        self.grid_cb.setChecked(True)
        self.grid_cb.toggled.connect(self._grid)
        tb.addWidget(self.grid_cb)
        dup = QAction(self)
        dup.setShortcut(QKeySequence("Ctrl+D"))
        dup.triggered.connect(self.duplicate)
        self.addAction(dup)

        self.surface.selected_changed.connect(self.show_props)
        self.surface.changed.connect(self.refresh_geometry_fields)
        self.surface.edit_requested.connect(lambda it: self.first_field and self.first_field.setFocus())
        self.fields = {}
        self.first_field = None
        self.apply_window()
        self.show_props(None)

    # ---------------- model ----------------
    def _grid(self, on):
        self.surface.show_grid = on
        self.surface.update()

    def next_name(self, t):
        used = {it.spec["name"] for it in self.surface.items}
        n = self.counter.get(t, 0)
        while True:
            n += 1
            name = f"{t}{n}"
            if name not in used:
                self.counter[t] = n
                return name

    def add_control(self, t, x=None, y=None):
        label, w, h = TYPE_INFO[t]
        name = self.next_name(t)
        if x is None:
            x, y = 20 + (len(self.surface.items) % 8) * 10, 20 + (len(self.surface.items) % 8) * 10
        spec = {"type": t, "name": name, "x": x, "y": y, "w": w, "h": h}
        if t in ("button", "statictext", "groupbox", "checkbox", "radiobutton"):
            spec["text"] = label if t != "statictext" else "Static text"
        if t in ("button", "bmpbutton", "listbox", "combobox"):
            spec["handler"] = f"[{name}Click]" if t in ("button", "bmpbutton") else f"[{name}Select]"
        if t in ("checkbox", "radiobutton"):
            spec["set"] = f"[{name}Set]"
            spec["reset"] = f"[{name}Reset]"
        if t in ("listbox", "combobox"):
            spec["array"] = f"{name}$"
        if t == "bmpbutton":
            spec["file"] = "bmp\\button.bmp"
        return self.surface.add(spec)

    def delete_selected(self):
        if self.surface.current:
            self.surface.remove(self.surface.current)

    def duplicate(self):
        it = self.surface.current
        if not it:
            return
        spec = dict(it.spec)
        spec["name"] = self.next_name(spec["type"])
        spec["x"] += 10
        spec["y"] += 10
        for k in ("handler", "set", "reset"):
            if k in spec:
                spec[k] = spec[k].replace(it.spec["name"], spec["name"])
        if "array" in spec:
            spec["array"] = spec["name"] + "$"
        self.surface.add(spec)

    def new_form(self):
        if self.surface.items and QMessageBox.question(self, "New form", "Remove all controls?") != QMessageBox.Yes:
            return
        self.surface.clear()
        self.counter.clear()

    def apply_window(self):
        w = self.win
        self.frame.title = w["title"]
        try:
            self.surface.form_font = parse_font(w["font"]) if w["font"].strip() else None
        except Exception:
            self.surface.form_font = None
        self.frame.set_client_size(max(60, w["w"] - FRAME_W), max(40, w["h"] - FRAME_H))
        for it in self.surface.items:
            it.rebuild()

    # ---------------- property editor ----------------
    def _clear_form(self):
        while self.form.rowCount():
            self.form.removeRow(0)
        self.fields = {}
        self.first_field = None

    def _line(self, label, value, on_change):
        e = QLineEdit(str(value))
        e.editingFinished.connect(lambda: on_change(e.text()))
        self.form.addRow(label, e)
        if self.first_field is None:
            self.first_field = e
        return e

    def _spin(self, label, value, on_change, lo=0, hi=4000):
        s = QSpinBox()
        s.setRange(lo, hi)
        s.setValue(int(value))
        s.valueChanged.connect(on_change)
        self.form.addRow(label, s)
        return s

    def show_props(self, it):
        self._clear_form()
        if it is None:
            w = self.win
            self.form.addRow(QLabel("<b>Window</b>"))
            self._line("Title:", w["title"], lambda v: self._set_win("title", v))
            self._line("Handle:  #", w["handle"], lambda v: self._set_win("handle", re.sub(r"\W", "", v) or "main"))
            cb = QComboBox()
            cb.addItems(WINDOW_TYPES)
            cb.setCurrentText(w["type"])
            cb.currentTextChanged.connect(lambda v: self._set_win("type", v))
            self.form.addRow("Type:", cb)
            self._spin("WindowWidth:", w["w"], lambda v: self._set_win("w", v), 80)
            self._spin("WindowHeight:", w["h"], lambda v: self._set_win("h", v), 60)
            self._line("Font:", w["font"], lambda v: self._set_win("font", v))
            c = QCheckBox("Center on screen")
            c.setChecked(w["center"])
            c.toggled.connect(lambda v: self.win.__setitem__("center", v))
            self.form.addRow("", c)
            self.form.addRow(QLabel("<small>Click a control to edit it. Click empty space for the window.</small>"))
            return
        s = it.spec
        label = TYPE_INFO[s["type"]][0]
        self.form.addRow(QLabel(f"<b>{label}</b>"))

        def setter(key, rebuild=True, fix=None):
            def f(v):
                it.spec[key] = fix(v) if fix else v
                if rebuild:
                    it.rebuild()
            return f
        self._line("Handle:  #" + self.win["handle"] + ".", s["name"],
                   setter("name", fix=lambda v: re.sub(r"[^\w.]", "", v) or s["name"]))
        if "text" in s:
            self._line("Text:", s["text"], setter("text"))
        if s["type"] == "bmpbutton":
            row = QWidget()
            hl = QHBoxLayout(row)
            hl.setContentsMargins(0, 0, 0, 0)
            e = QLineEdit(s["file"])
            e.editingFinished.connect(lambda: setter("file")(e.text()))
            b = QPushButton("…")
            b.setFixedWidth(30)
            b.clicked.connect(lambda: self._pick_bmp(it, e))
            hl.addWidget(e)
            hl.addWidget(b)
            self.form.addRow("Bitmap file:", row)
        if "handler" in s:
            self._line("Branch label:", s["handler"], setter("handler", False, self._fix_label))
        if "set" in s:
            self._line("When set:", s["set"], setter("set", False, self._fix_label))
            self._line("When reset:", s["reset"], setter("reset", False, self._fix_label))
        if "array" in s:
            self._line("Items array:", s["array"], setter("array", fix=lambda v: v.strip().rstrip("()") or "items$"))
        self.fields["x"] = self._spin("X:", s["x"], lambda v: self._geo(it, "x", v))
        self.fields["y"] = self._spin("Y:", s["y"], lambda v: self._geo(it, "y", v))
        self.fields["w"] = self._spin("Width:", s["w"], lambda v: self._geo(it, "w", v), 5)
        self.fields["h"] = self._spin("Height:", s["h"], lambda v: self._geo(it, "h", v), 5)

    @staticmethod
    def _fix_label(v):
        v = v.strip()
        if not v:
            return ""
        if re.match(r"^[A-Za-z][\w.]*$", v) and not v.startswith("["):
            return v  # a SUB name
        return "[" + v.strip("[]") + "]"

    def _pick_bmp(self, it, edit):
        base = os.path.dirname(self.ide.current_tab().path or "") or os.path.expanduser("~")
        f, _ = QFileDialog.getOpenFileName(self, "Bitmap for button", base, "Bitmaps (*.bmp *.png);;All files (*)")
        if f:
            rel = os.path.relpath(f, base) if self.ide.current_tab().path else f
            if rel.startswith(".."):
                rel = f
            it.spec["file"] = rel.replace("/", "\\")
            it.spec["file_real"] = f
            pm = QPixmap(f)
            if not pm.isNull():
                it.spec["w"], it.spec["h"] = pm.width() + 4, pm.height() + 4
            edit.setText(it.spec["file"])
            it.rebuild()
            self.refresh_geometry_fields()

    def _geo(self, it, key, v):
        it.spec[key] = v
        it.place()

    def refresh_geometry_fields(self):
        it = self.surface.current
        if not it or not self.fields:
            return
        for k, f in self.fields.items():
            if f.value() != it.spec[k]:
                f.blockSignals(True)
                f.setValue(it.spec[k])
                f.blockSignals(False)

    def _set_win(self, key, v):
        self.win[key] = v
        self.apply_window()

    # ---------------- code generation ----------------
    def code(self, existing=""):
        w = self.win
        h = "#" + w["handle"]
        lines = ["    nomainwin", f"    WindowWidth = {w['w']}", f"    WindowHeight = {w['h']}"]
        if w["center"]:
            lines += ["    UpperLeftX = int((DisplayWidth-WindowWidth)/2)",
                      "    UpperLeftY = int((DisplayHeight-WindowHeight)/2)"]
        lines.append("")
        arrays = [it.spec["array"] for it in self.surface.items if "array" in it.spec]
        for a in arrays:
            lines.append(f"    dim {a}(10)")
        if arrays:
            lines.append("")
        handlers = []
        for it in sorted(self.surface.items, key=lambda i: (i.spec["type"] != "groupbox",
                                                           self.surface.items.index(i))):
            s = it.spec
            t = s["type"]
            ch = f"{h}.{s['name']}"
            geo = f"{s['x']}, {s['y']}, {s['w']}, {s['h']}"
            q = '"' + s.get("text", "").replace('"', "'") + '"'
            hd = s.get("handler") or "[nothing]"
            if t == "button":
                lines.append(f"    button {ch}, {q}, {hd}, UL, {geo}")
            elif t == "bmpbutton":
                lines.append(f"    bmpbutton {ch}, \"{s['file']}\", {hd}, UL, {s['x']}, {s['y']}")
            elif t in ("textbox", "texteditor", "graphicbox"):
                lines.append(f"    {t} {ch}, {geo}")
            elif t in ("statictext", "groupbox"):
                lines.append(f"    {t} {ch}, {q}, {geo}")
            elif t in ("listbox", "combobox"):
                lines.append(f"    {t} {ch}, {s['array']}(), {hd}, {geo}")
            elif t in ("checkbox", "radiobutton"):
                lines.append(f"    {t} {ch}, {q}, {s['set'] or '[nothing]'}, {s['reset'] or '[nothing]'}, {geo}")
            for k in ("handler", "set", "reset"):
                if s.get(k):
                    handlers.append((s[k], t, s["name"], k))
        lines.append(f"    open \"{w['title']}\" for {w['type']} as {h}")
        if w["font"].strip() and not w["type"].startswith("graphics"):
            lines.append(f"    print {h}, \"font {w['font']}\"")
        quit_label = f"[quit.{w['handle']}]"
        lines.append(f"    print {h}, \"trapclose {quit_label}\"")
        lines += ["", f"[{w['handle']}.inputLoop]   'wait here for input event", "    wait", ""]
        if self.stubs.isChecked():
            existing_labels = {m.lower() for m in re.findall(r"^\s*(\[[^\]]+\])", existing, re.M)}
            done = set()
            uses_nothing = False
            for label, t, name, kind in handlers:
                if label == "[nothing]":
                    uses_nothing = True
                    continue
                if not label.startswith("["):
                    if label.lower() in done:
                        continue
                    done.add(label.lower())
                    lines += [f"sub {label} handle$", "    'Insert your own code here", "end sub", ""]
                    continue
                if label.lower() in existing_labels or label.lower() in done:
                    continue
                done.add(label.lower())
                what = {"handler": "Perform action for", "set": "Checked:", "reset": "Unchecked:"}[kind]
                lines += [f"{label}   '{what} the {t} named '{name}'", "    'Insert your own code here", "    wait", ""]
            if uses_nothing and "[nothing]" not in existing_labels:
                lines += ["[nothing]", "    wait", ""]
            if quit_label.lower() not in existing_labels:
                lines += [f"{quit_label} 'End the program", f"    close {h}", "    end", ""]
        return "\n".join(lines) + "\n"

    def generate(self, new_tab):
        ed = self.ide.current_editor()
        existing = ed.toPlainText() if (ed and not new_tab) else ""
        self.ide.insert_code(self.code(existing), new_tab=new_tab)
        self.ide.statusBar().showMessage("FreeForm code inserted", 4000)

    def copy_code(self):
        QApplication.clipboard().setText(self.code())
        self.statusBar().showMessage("Code copied to the clipboard", 3000)

    # ---------------- import ----------------
    def import_from_editor(self):
        ed = self.ide.current_editor()
        if not ed:
            return
        text = ed.textCursor().selectedText().replace(" ", "\n") or ed.toPlainText()
        self.import_code(text)

    def import_code(self, text):
        try:
            stmts = parse(text)
        except Exception as e:
            QMessageBox.warning(self, "Import", f"Couldn't read that code: {e}")
            return
        specs = []
        win = dict(self.win)

        def lit(node):
            if node is None:
                return None
            if node[0] in ("num", "str"):
                return node[1]
            if node[0] == "un" and node[1] == "-" and node[2][0] == "num":
                return -node[2][1]
            return None

        def handler(a):
            if a[0] == "label":
                return f"[{a[1]}]"
            if a[0] == "e" and a[1][0] == "var":
                return a[1][1]
            return ""
        found_open = False
        for st in stmts:
            if st.kind == "assign" and st.target[0] == "var":
                n = st.target[1].lower()
                v = lit(st.expr)
                if n == "windowwidth" and isinstance(v, (int, float)):
                    win["w"] = int(v)
                elif n == "windowheight" and isinstance(v, (int, float)):
                    win["h"] = int(v)
            elif st.kind == "control" and st.ctype != "menu":
                raw = st.handle[1]
                name = raw.split(".", 1)[1] if "." in raw else raw.lstrip("#")
                args = st.args
                vals = [lit(a[1]) if a[0] == "e" else None for a in args]
                t = st.ctype
                spec = {"type": t, "name": name}
                try:
                    if t == "button":
                        spec.update(text=str(vals[0] or ""), handler=handler(args[1]),
                                    x=int(vals[3] or 0), y=int(vals[4] or 0),
                                    w=int(vals[5]) if len(vals) > 5 and vals[5] else 100,
                                    h=int(vals[6]) if len(vals) > 6 and vals[6] else 25)
                    elif t == "bmpbutton":
                        spec.update(file=str(vals[0] or ""), handler=handler(args[1]), x=int(vals[3] or 0),
                                    y=int(vals[4] or 0), w=40, h=40)
                        base = os.path.dirname(self.ide.current_tab().path or "")
                        from .. import paths
                        real = paths.resolve(spec["file"], base or os.getcwd(), must_exist=True)
                        if os.path.exists(real):
                            spec["file_real"] = real
                            pm = QPixmap(real)
                            if not pm.isNull():
                                spec["w"], spec["h"] = pm.width() + 4, pm.height() + 4
                    elif t in ("textbox", "texteditor", "graphicbox"):
                        spec.update(x=int(vals[0]), y=int(vals[1]), w=int(vals[2]), h=int(vals[3]))
                    elif t in ("statictext", "groupbox"):
                        spec.update(text=str(vals[0] or ""), x=int(vals[1]), y=int(vals[2]), w=int(vals[3]),
                                    h=int(vals[4]))
                    elif t in ("listbox", "combobox"):
                        arr = args[0][1][1] if args[0][0] == "e" else "items$"
                        spec.update(array=arr, handler=handler(args[1]), x=int(vals[2]), y=int(vals[3]),
                                    w=int(vals[4]), h=int(vals[5]))
                    elif t in ("checkbox", "radiobutton"):
                        spec.update(text=str(vals[0] or ""), set=handler(args[1]), reset=handler(args[2]),
                                    x=int(vals[3]), y=int(vals[4]), w=int(vals[5]), h=int(vals[6]))
                except (TypeError, ValueError, IndexError):
                    continue  # positions computed at run time can't be imported
                specs.append(spec)
            elif (st.kind == "print" and st.handle and len(st.items) == 1 and st.items[0][0] == "e"
                  and st.items[0][1][0] == "str" and st.items[0][1][1].lower().startswith("font ")
                  and "." not in st.handle[1]):
                win["font"] = st.items[0][1][1][5:].strip()
            elif st.kind == "open" and not found_open and st.mode.split("_")[0] in ("window", "dialog", "graphics"):
                title = lit(st.name)
                if isinstance(title, str):
                    win["title"] = title
                win["type"] = st.mode if st.mode in WINDOW_TYPES else win["type"]
                win["handle"] = st.handle[1].lstrip("#").split(".")[0]
                found_open = True
                if specs:
                    break  # first window only
        if not specs and not found_open:
            QMessageBox.information(self, "Import", "No window or control statements found in the selection.")
            return
        self.surface.clear()
        self.win = win
        self.apply_window()
        for s in specs:
            self.surface.add(s, select=False)
        self.show_props(None)
        self.statusBar().showMessage(f"Imported {len(specs)} control(s)", 4000)

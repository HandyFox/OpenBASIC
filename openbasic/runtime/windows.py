"""Program windows (window, dialog, graphics, text) and the mainwin console."""
import sys

from PySide6.QtCore import QEventLoop, Qt, QTimer
from PySide6.QtGui import QAction, QFont, QFontDatabase, QFontMetrics, QGuiApplication, QKeySequence, QTextCursor
from PySide6.QtWidgets import QMainWindow, QPlainTextEdit, QVBoxLayout, QWidget

from ..errors import BasicError
from .controls import CONTROL_CLASSES, apply_colors, common_cmd, text_edit_command
from .graphics import GraphicsView
from .style import css_color, default_font, parse_color, parse_font, program_palette

IS_MAC = sys.platform == "darwin"
# Just BASIC's WindowWidth/WindowHeight include the frame, title bar and menu bar.
# Most programs were laid out on classic Windows, whose chrome was this size.
FRAME_W = 8
FRAME_H = 27
MENU_H = 19


class AbsoluteArea(QWidget):
    """Client area with absolutely positioned controls (anchored to a corner)."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.items = []

    def _place(self, widget, rect, corner, shift=(0, 0)):
        x, y, w, h = rect
        W, H = self.width(), self.height()
        if corner in ("ur", "lr"):
            x = W - x - w - shift[0]
        if corner in ("ll", "lr"):
            y = H - y - h - shift[1]
        widget.setGeometry(int(x), int(y), int(w), int(h))

    def relayout(self):
        """Place corner-anchored controls. Controls anchored to the same corner keep their
        spacing; if the program's offsets would push them past the window edge (common in
        programs written for older Windows), the whole group slides back inside."""
        W, H = self.width(), self.height()
        for corner in ("ur", "ll", "lr"):
            group = [(w, r) for w, r, c in self.items if c == corner]
            if not group:
                continue
            sx = sy = 0
            if corner in ("ur", "lr"):
                sx = max(0, max(-(r[0]) for w, r in group))  # right edge beyond the window
            if corner in ("ll", "lr"):
                sy = max(0, max(-(r[1]) for w, r in group))
            for w, r in group:
                self._place(w, r, corner, (sx, sy))

    def add(self, widget, rect, corner):
        self.items.append((widget, rect, corner))
        if corner == "ul":
            self._place(widget, rect, corner)
        else:
            self.relayout()

    def resizeEvent(self, ev):
        super().resizeEvent(ev)
        self.relayout()


class BasicWindow(QMainWindow):
    def __init__(self, host, key, title, mode, settings, controls, menus):
        super().__init__()
        self.host = host
        self.key = key
        parts = mode.split("_")
        self.base = parts[0]
        self.flags = set(parts[1:])
        if self.base not in ("window", "dialog", "graphics", "text"):
            raise BasicError(f"Unknown window type '{mode}'")
        self.controls = {}
        self.trapclose = None
        self.resize_handler = None
        self.closing_by_program = False
        self.setWindowTitle(title)
        self.setPalette(program_palette())
        self.setAttribute(Qt.WA_DeleteOnClose, False)
        self.setFont(default_font())

        flags = self.windowFlags()
        if self.base == "dialog":
            flags = (flags | Qt.Dialog | Qt.WindowCloseButtonHint) & ~Qt.WindowMinMaxButtonsHint
        if "popup" in self.flags:
            flags |= Qt.FramelessWindowHint
        self.setWindowFlags(flags)
        if "modal" in self.flags:
            self.setWindowModality(Qt.ApplicationModal)

        self.area = AbsoluteArea()
        self.view = None
        self.editor = None
        if self.base == "graphics":
            lay = QVBoxLayout(self.area)
            lay.setContentsMargins(0, 0, 0, 0)
            self.view = GraphicsView(host, key, self.area, settings["width"], settings["height"])
            lay.addWidget(self.view)
        elif self.base == "text":
            lay = QVBoxLayout(self.area)
            lay.setContentsMargins(0, 0, 0, 0)
            self.editor = QPlainTextEdit(self.area)
            mono = QFontDatabase.systemFont(QFontDatabase.FixedFont)
            self.editor.setFont(mono)
            lay.addWidget(self.editor)
        self.setCentralWidget(self.area)

        bg = settings.get("bg")
        if bg:
            self.area.setAutoFillBackground(True)
            pal = self.area.palette()
            pal.setColor(self.area.backgroundRole(), parse_color(bg))
            self.area.setPalette(pal)

        for title_, items in menus:
            m = self.menuBar().addMenu(title_)
            for it in items:
                if it is None:
                    m.addSeparator()
                    continue
                text, handler = it
                act = QAction(text, self)
                act.triggered.connect(lambda _=False, h=handler: host.push_event(h, [key], {}, key))
                m.addAction(act)
        if self.base == "text" and not menus:
            m = self.menuBar().addMenu("&Edit")
            for label, fn, seq in (("Cu&t", self.editor.cut, QKeySequence.Cut),
                                   ("&Copy", self.editor.copy, QKeySequence.Copy),
                                   ("&Paste", self.editor.paste, QKeySequence.Paste),
                                   ("Select &All", self.editor.selectAll, QKeySequence.SelectAll)):
                a = QAction(label, self)
                a.setShortcut(seq)
                a.triggered.connect(fn)
                m.addAction(a)

        for spec in controls:
            self.add_control(spec, settings)

        cw = max(60, settings["width"] - FRAME_W)
        ch = max(40, settings["height"] - FRAME_H)
        if self.menuBar().actions():
            # the menu bar comes out of the window height, as on Windows; our menu bar
            # may be taller than the classic one, so grow the window by the difference
            mh = self.menuBar().sizeHint().height()
            ch = ch - MENU_H + (mh if not IS_MAC else 0)
        self.resize(cw, ch)
        if "nf" in self.flags or self.base == "dialog":
            self.setFixedSize(cw, ch)
        x, y = settings.get("x", 0), settings.get("y", 0)
        if x or y:
            self.move(x, y)
        else:
            scr = QGuiApplication.primaryScreen()
            if scr:
                g = scr.availableGeometry()
                self.move(g.x() + max(0, (g.width() - cw) // 2), g.y() + max(0, (g.height() - ch) // 3))

    def add_control(self, spec, settings):
        raw = spec["raw"]
        if "." in raw:
            ext = raw.split(".", 1)[1]
        else:
            # "button #calc, ..." with no extension: Just BASIC allows it; give it a private name
            self._anon = getattr(self, "_anon", 0) + 1
            ext = f"_{spec['type']}{self._anon}"
        ckey = (self.key + "." + ext).lower()
        cls = CONTROL_CLASSES.get(spec["type"])
        if cls is None:
            raise BasicError(f"Unknown control type {spec['type']}")
        ctl = cls(self.host, self, ckey, spec, self.area)
        apply_colors(ctl, settings)
        self.area.add(ctl.widget, ctl.rect, ctl.corner)
        self.controls[ckey] = ctl
        return ctl

    # ---- commands sent to the window handle itself ----
    def command(self, text, lookup, newline):
        cmd = text.strip()
        words = cmd.lstrip("!").split()
        op = words[0].lower() if words else ""
        args = words[1:]
        if op == "trapclose":
            h = args[0] if args else None
            self.trapclose = (("label", h.strip("[]").lower()) if h.startswith("[") else ("sub", h)) if h else None
            return None
        if op == "resizehandler":
            h = args[0] if args else None
            self.resize_handler = (("label", h.strip("[]").lower()) if h.startswith("[") else ("sub", h)) if h else None
            return None
        if self.base == "text":
            return text_edit_command(self.editor, text, lookup, newline)
        if self.base == "graphics":
            if op == "font":
                self.view.command(cmd, lookup)
                return None
            return self.view.command(text, lookup)
        if not words:
            return None
        if op == "font":
            f = parse_font(" ".join(args))
            self.area.setFont(f)
            for c in self.controls.values():
                c.widget.setFont(f)
                if hasattr(c, "update_wrap"):
                    c.update_wrap()
            return None
        if op == "close":
            self.host.close_gui(self.key)
            return None
        if op in ("show", "hide", "setfocus", "refresh", "enable", "disable"):
            common_cmd(self, op, args)
            return None
        if op == "locate":
            x, y, w, h = (int(float(a)) for a in args[:4])
            self.setGeometry(x, y, max(60, w - FRAME_W), max(40, h - FRAME_H))
            return None
        raise BasicError(f"Unknown window command '{cmd}' for {self.key}")

    def closeEvent(self, ev):
        if self.closing_by_program:
            ev.accept()
            return
        if self.trapclose:
            ev.ignore()
            self.host.push_event(self.trapclose, [self.key], {}, self.key)
            return
        ev.accept()
        self.host.window_closed_by_user(self.key)

    def resizeEvent(self, ev):
        super().resizeEvent(ev)
        if self.resize_handler:
            self.host.push_event(self.resize_handler, [self.key],
                                 {"WindowWidth": self.width() + FRAME_W,
                                  "WindowHeight": self.height() + FRAME_H}, self.key, coalesce=True)


class ConsoleEdit(QPlainTextEdit):
    def __init__(self, console):
        super().__init__()
        self.console = console
        self.setReadOnly(True)
        self.setUndoRedoEnabled(False)
        self.setLineWrapMode(QPlainTextEdit.WidgetWidth)
        self.input_start = None

    def keyPressEvent(self, ev):
        c = self.console
        if self.input_start is None:
            from .keys import inkey_for
            k = inkey_for(ev)
            if ev.matches(QKeySequence.Copy) or ev.matches(QKeySequence.SelectAll):
                super().keyPressEvent(ev)
                return
            if k is not None:
                c.host.set_inkey(k)
                c.keys.append(k)
                if c.char_loop is not None:
                    c.char_loop.quit()
            return
        cur = self.textCursor()
        if cur.position() < self.input_start:
            cur.movePosition(QTextCursor.End)
            self.setTextCursor(cur)
        if ev.key() in (Qt.Key_Return, Qt.Key_Enter):
            doc_text = self.toPlainText()
            text = doc_text[self.input_start:]
            cur.movePosition(QTextCursor.End)
            self.setTextCursor(cur)
            self.insertPlainText("\n")
            self.input_start = None
            self.setReadOnly(True)
            c.input_result = text
            if c.input_loop is not None:
                c.input_loop.quit()
            return
        if ev.key() == Qt.Key_Backspace and cur.position() <= self.input_start and not cur.hasSelection():
            return
        if ev.key() in (Qt.Key_Up, Qt.Key_PageUp, Qt.Key_Home) and not ev.modifiers():
            cur.setPosition(self.input_start)
            self.setTextCursor(cur)
            return
        super().keyPressEvent(ev)


class ConsoleWindow(QMainWindow):
    """The 'mainwin' text console."""

    def __init__(self, host, title):
        super().__init__()
        self.host = host
        self.setWindowTitle(title)
        self.setPalette(program_palette())
        self.edit = ConsoleEdit(self)
        f = QFontDatabase.systemFont(QFontDatabase.FixedFont)
        f.setPointSize(11 if IS_MAC else 10)
        self.edit.setFont(f)
        self.edit.setStyleSheet("QPlainTextEdit { background: white; color: black; }")
        self.setCentralWidget(self.edit)
        fm = QFontMetrics(f)
        self.resize(fm.horizontalAdvance("M") * 82 + 30, fm.lineSpacing() * 26 + 20)
        self.col = 0
        self.input_loop = None
        self.input_result = None
        self.char_loop = None
        self.keys = []
        self.overwrite = None  # (block, col) after LOCATE
        self.program_running = True

    def write(self, text):
        e = self.edit
        cur = e.textCursor()
        if self.overwrite is not None:
            for i, ch in enumerate(text):
                if ch == "\n":
                    # leave overwrite mode: the rest goes at the end like normal output
                    self.overwrite = None
                    cur.movePosition(QTextCursor.End)
                    cur.insertText(text[i:])
                    break
                if not cur.atBlockEnd():
                    cur.movePosition(QTextCursor.Right, QTextCursor.KeepAnchor, 1)
                cur.insertText(ch)
        else:
            cur.movePosition(QTextCursor.End)
            cur.insertText(text)
        e.setTextCursor(cur)
        e.ensureCursorVisible()
        self._track(text)

    def _track(self, text):
        nl = text.rfind("\n")
        self.col = len(text) - nl - 1 if nl >= 0 else self.col + len(text)

    def cls(self):
        self.edit.clear()
        self.col = 0
        self.overwrite = None

    def locate(self, x, y):
        doc = self.edit.document()
        while doc.blockCount() < y:
            c = QTextCursor(doc)
            c.movePosition(QTextCursor.End)
            c.insertText("\n")
        block = doc.findBlockByNumber(max(0, y - 1))
        c = QTextCursor(block)
        line_len = len(block.text())
        if line_len < x - 1:
            c.movePosition(QTextCursor.EndOfBlock)
            c.insertText(" " * (x - 1 - line_len))
        c = QTextCursor(block)
        c.movePosition(QTextCursor.Right, QTextCursor.MoveAnchor, max(0, x - 1))
        self.edit.setTextCursor(c)
        self.overwrite = True
        self.col = x - 1

    def read_line(self, prompt):
        self.write(prompt)
        self.overwrite = None
        e = self.edit
        cur = e.textCursor()
        cur.movePosition(QTextCursor.End)
        e.setTextCursor(cur)
        e.input_start = cur.position()
        e.setReadOnly(False)
        self.show()
        self.raise_()
        self.activateWindow()
        e.setFocus()
        self.input_result = None
        while self.input_result is None:
            self.input_loop = QEventLoop()
            self.host.active_loops.append(self.input_loop)
            try:
                self.input_loop.exec()
            finally:
                self.host.active_loops.remove(self.input_loop)
                self.input_loop = None
            self.host.check_stop()
        self.col = 0
        return self.input_result

    def read_chars(self, n):
        self.show()
        self.edit.setFocus()
        out = ""
        while len(out) < n:
            while not self.keys:
                self.char_loop = QEventLoop()
                self.host.active_loops.append(self.char_loop)
                try:
                    self.char_loop.exec()
                finally:
                    self.host.active_loops.remove(self.char_loop)
                    self.char_loop = None
                self.host.check_stop()
            out += self.keys.pop(0)
        return out

    def closeEvent(self, ev):
        if self.program_running:
            self.host.console_closed()
        ev.accept()

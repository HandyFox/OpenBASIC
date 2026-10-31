"""OpenBASIC IDE main window."""
import os
import sys

from PySide6.QtCore import QSettings, QSize, Qt, QTimer
from PySide6.QtGui import QAction, QFont, QIcon, QKeySequence, QTextCursor, QTextDocument
from PySide6.QtWidgets import (QApplication, QCheckBox, QComboBox, QDialog, QDockWidget, QFileDialog,
                               QHBoxLayout, QHeaderView, QInputDialog, QLabel, QLineEdit, QListWidget,
                               QMainWindow, QMessageBox, QPlainTextEdit, QPushButton, QStyle, QTabWidget,
                               QToolBar, QTreeWidget, QTreeWidgetItem, QVBoxLayout, QWidget)

from .. import __version__
from ..errors import BasicError
from ..host_base import Host
from ..interp import Debugger, Interpreter
from ..values import to_str
from . import icons, theme
from .editor import CodeEditor

FILE_FILTER = "BASIC programs (*.bas *.bak *.txt);;All files (*)"
EXAMPLES_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "examples")


def read_source(path):
    with open(path, "rb") as f:
        data = f.read()
    try:
        text = data.decode("utf-8")
        enc = "utf-8"
    except UnicodeDecodeError:
        text = data.decode("cp1252", errors="replace")
        enc = "cp1252"
    newline = "\r\n" if b"\r\n" in data else "\n"
    return text.replace("\r\n", "\n").replace("\r", "\n"), enc, newline


class EditorTab(QWidget):
    def __init__(self, main, path=None, text=""):
        super().__init__()
        self.main = main
        self.path = path
        self.encoding = "utf-8"
        self.newline = "\r\n" if os.name == "nt" else "\n"
        self.editor = CodeEditor(self)
        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.addWidget(self.editor)
        self.editor.setPlainText(text)
        self.editor.document().setModified(False)
        self.editor.apply_theme()
        self.editor.set_font_size(main.font_size)

    def title(self):
        name = os.path.basename(self.path) if self.path else "untitled.bas"
        return name + (" *" if self.editor.document().isModified() else "")

    def save(self, path=None):
        path = path or self.path
        text = self.editor.toPlainText().replace("\n", self.newline)
        try:
            data = text.encode(self.encoding)
        except UnicodeEncodeError:
            data = text.encode("utf-8")
            self.encoding = "utf-8"
        with open(path, "wb") as f:
            f.write(data)
        self.path = path
        self.editor.document().setModified(False)


class FindBar(QWidget):
    def __init__(self, main):
        super().__init__()
        self.main = main
        lay = QHBoxLayout(self)
        lay.setContentsMargins(6, 3, 6, 3)
        self.find = QLineEdit()
        self.find.setPlaceholderText("Find")
        self.replace = QLineEdit()
        self.replace.setPlaceholderText("Replace with")
        self.case = QCheckBox("Match case")
        b_next = QPushButton("Next")
        b_prev = QPushButton("Previous")
        b_rep = QPushButton("Replace")
        b_all = QPushButton("Replace all")
        b_close = QPushButton("✕")
        b_close.setFlat(True)
        b_close.setFixedWidth(28)
        for w in (QLabel("Find:"), self.find, b_next, b_prev, self.case, self.replace, b_rep, b_all, b_close):
            lay.addWidget(w)
        self.find.returnPressed.connect(lambda: self.go(True))
        b_next.clicked.connect(lambda: self.go(True))
        b_prev.clicked.connect(lambda: self.go(False))
        b_rep.clicked.connect(self.replace_one)
        b_all.clicked.connect(self.replace_all)
        b_close.clicked.connect(self.hide)

    def editor(self):
        return self.main.current_editor()

    def flags(self, forward=True):
        f = QTextDocument.FindFlag(0)
        if self.case.isChecked():
            f |= QTextDocument.FindCaseSensitively
        if not forward:
            f |= QTextDocument.FindBackward
        return f

    def go(self, forward=True):
        ed = self.editor()
        if not ed or not self.find.text():
            return False
        if ed.find(self.find.text(), self.flags(forward)):
            return True
        c = ed.textCursor()
        c.movePosition(QTextCursor.Start if forward else QTextCursor.End)
        ed.setTextCursor(c)
        found = ed.find(self.find.text(), self.flags(forward))
        if not found:
            self.main.statusBar().showMessage(f"'{self.find.text()}' not found", 3000)
        return found

    def replace_one(self):
        ed = self.editor()
        if not ed:
            return
        c = ed.textCursor()
        sel = c.selectedText()
        target = self.find.text()
        same = sel == target if self.case.isChecked() else sel.lower() == target.lower()
        if c.hasSelection() and same:
            c.insertText(self.replace.text())
        self.go(True)

    def replace_all(self):
        ed = self.editor()
        if not ed or not self.find.text():
            return
        c = ed.textCursor()
        c.beginEditBlock()
        c.movePosition(QTextCursor.Start)
        ed.setTextCursor(c)
        n = 0
        while ed.find(self.find.text(), self.flags(True)):
            ed.textCursor().insertText(self.replace.text())
            n += 1
        c.endEditBlock()
        self.main.statusBar().showMessage(f"Replaced {n} occurrence(s)", 4000)

    def open(self):
        ed = self.editor()
        if ed and ed.textCursor().hasSelection():
            self.find.setText(ed.textCursor().selectedText())
        self.show()
        self.find.setFocus()
        self.find.selectAll()


class MainWindow(QMainWindow):
    def __init__(self, files=()):
        super().__init__()
        self.settings = QSettings("OpenBASIC", "OpenBASIC")
        self.font_size = int(self.settings.value("font_size", 11))
        theme.apply(self.settings.value("theme", "light"))
        self.running = False
        self.paused = False
        self.host = None
        self.interp = None
        self.debugger = None
        self.paused_frame = None
        self.last_host = None
        self.anim_delay = float(self.settings.value("anim_delay", 0.3))
        self.setWindowTitle("OpenBASIC")
        self.setWindowIcon(icons.app_icon())
        self.resize(1100, 760)

        self.tabs = QTabWidget()
        self.tabs.setTabsClosable(True)
        self.tabs.setMovable(True)
        self.tabs.setDocumentMode(True)
        self.tabs.tabCloseRequested.connect(self.close_tab)
        self.tabs.currentChanged.connect(self.on_tab_changed)
        self.findbar = FindBar(self)
        self.findbar.hide()
        center = QWidget()
        lay = QVBoxLayout(center)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(0)
        lay.addWidget(self.tabs)
        lay.addWidget(self.findbar)
        self.setCentralWidget(center)

        self.label_timer = QTimer(self)
        self.label_timer.setSingleShot(True)
        self.label_timer.timeout.connect(self.refresh_labels)

        self._build_actions()
        self._build_menus()
        self._build_toolbar()
        self._build_docks()
        self.statusBar().showMessage("Ready")
        self.setAcceptDrops(True)

        geo = self.settings.value("geometry")
        if geo is not None:
            self.restoreGeometry(geo)
        opened = False
        for f in files:
            if os.path.exists(f):
                self.open_file(f)
                opened = True
        if not opened:
            for f in self.settings.value("session", []) or []:
                if isinstance(f, str) and os.path.exists(f):
                    self.open_file(f)
                    opened = True
        if not opened:
            self.new_file()
        self.update_actions()

    # ------------------------------------------------------------- building
    def _act(self, text, slot, shortcut=None, icon=None, tip=None, checkable=False):
        a = QAction(text, self)
        if shortcut:
            a.setShortcut(QKeySequence(shortcut) if isinstance(shortcut, str) else shortcut)
        if icon:
            a.setIcon(icons.icon(icon))
        if tip:
            a.setToolTip(tip)
            a.setStatusTip(tip)
        a.setCheckable(checkable)
        a.triggered.connect(slot)
        return a

    def _build_actions(self):
        self.a_new = self._act("&New", self.new_file, QKeySequence.New, "new", "New program")
        self.a_open = self._act("&Open…", self.open_dialog, QKeySequence.Open, "open", "Open a program")
        self.a_save = self._act("&Save", self.save, QKeySequence.Save, "save", "Save")
        self.a_save_as = self._act("Save &As…", self.save_as, QKeySequence.SaveAs)
        self.a_close = self._act("&Close Tab", lambda: self.close_tab(self.tabs.currentIndex()), QKeySequence.Close)
        self.a_quit = self._act("E&xit", self.close, QKeySequence.Quit)
        self.a_undo = self._act("&Undo", lambda: self.current_editor().undo(), QKeySequence.Undo)
        self.a_redo = self._act("&Redo", lambda: self.current_editor().redo(), QKeySequence.Redo)
        self.a_cut = self._act("Cu&t", lambda: self.current_editor().cut(), QKeySequence.Cut)
        self.a_copy = self._act("&Copy", lambda: self.current_editor().copy(), QKeySequence.Copy)
        self.a_paste = self._act("&Paste", lambda: self.current_editor().paste(), QKeySequence.Paste)
        self.a_selall = self._act("Select &All", lambda: self.current_editor().selectAll(), QKeySequence.SelectAll)
        self.a_find = self._act("&Find / Replace…", self.findbar.open, QKeySequence.Find, "find", "Find and replace")
        self.a_findnext = self._act("Find &Next", lambda: self.findbar.go(True), QKeySequence.FindNext)
        self.a_goto = self._act("&Go to Line…", self.goto_line, "Ctrl+G")
        self.a_comment = self._act("Toggle &Comment", lambda: self.current_editor().toggle_comment(), "Ctrl+/")
        self.a_indent = self._act("&Indent", lambda: self.current_editor().indent_selection(1), "Ctrl+]")
        self.a_outdent = self._act("&Outdent", lambda: self.current_editor().indent_selection(-1), "Ctrl+[")

        self.a_run = self._act("&Run", self.run_clicked, "F5", "run", "Run (F5)")
        self.a_debug = self._act("&Debug", lambda: self.start_run(debug=True, step_first=True), "F7", "debug",
                                 "Debug: start paused on the first line (F7)")
        self.a_stop = self._act("&Stop", self.stop, "Shift+F5", "stop", "Stop the program (Shift+F5)")
        self.a_pause = self._act("&Pause", self.pause, "Ctrl+F5", "pause", "Pause at the next statement")
        self.a_step = self._act("Step &Into", lambda: self.step("step"), "F8", "step_into", "Step into (F8)")
        self.a_over = self._act("Step &Over", lambda: self.step("over"), "F10", "step_over", "Step over GOSUB/CALL (F10)")
        self.a_out = self._act("Step O&ut", lambda: self.step("out"), "Shift+F11", "step_out", "Run until RETURN / END SUB (Shift+F11)")
        self.a_animate = self._act("&Animate", lambda: self.step("animate"), "Ctrl+F8", "animate",
                                   "Run slowly, highlighting each line")
        self.a_bp = self._act("Toggle &Breakpoint", lambda: self.current_editor().toggle_breakpoint(), "F9", "breakpoint",
                              "Toggle breakpoint (F9) — or click the line number")
        self.a_clear_bp = self._act("&Clear All Breakpoints", self.clear_breakpoints)
        self.a_check = self._act("Check S&yntax", self.check_syntax, "Ctrl+F7", "check", "Check for errors without running")

        self.a_designer = self._act("&FreeForm GUI Designer…", self.open_designer, "Ctrl+Shift+D", "designer",
                                    "Design a window by dragging controls")
        self.a_package = self._act("Make &Standalone App…", self.open_packager, None, "package",
                                   "Package this program so it runs without OpenBASIC")

        self.a_dark = self._act("&Dark Theme", self.toggle_theme, checkable=True)
        self.a_dark.setChecked(theme.current_name == "dark")
        self.a_bigger = self._act("&Bigger Text", lambda: self.change_font(1), QKeySequence.ZoomIn)
        self.a_smaller = self._act("&Smaller Text", lambda: self.change_font(-1), QKeySequence.ZoomOut)
        self.a_about = self._act("&About OpenBASIC", self.about)

    def _build_menus(self):
        mb = self.menuBar()
        m = mb.addMenu("&File")
        for a in (self.a_new, self.a_open):
            m.addAction(a)
        self.recent_menu = m.addMenu("Open &Recent")
        self.examples_menu = m.addMenu("Open &Example")
        self._fill_examples()
        m.addSeparator()
        for a in (self.a_save, self.a_save_as, self.a_close):
            m.addAction(a)
        m.addSeparator()
        m.addAction(self.a_package)
        m.addSeparator()
        m.addAction(self.a_quit)
        self.recent_menu.aboutToShow.connect(self._fill_recent)

        m = mb.addMenu("&Edit")
        for a in (self.a_undo, self.a_redo, None, self.a_cut, self.a_copy, self.a_paste, self.a_selall, None,
                  self.a_find, self.a_findnext, self.a_goto, None, self.a_comment, self.a_indent, self.a_outdent):
            m.addSeparator() if a is None else m.addAction(a)

        m = mb.addMenu("&Run")
        for a in (self.a_run, self.a_debug, self.a_stop, None, self.a_pause, self.a_step, self.a_over, self.a_out,
                  self.a_animate, None, self.a_bp, self.a_clear_bp, None, self.a_check):
            m.addSeparator() if a is None else m.addAction(a)
        speed = m.addMenu("Animate Speed")
        for label, d in (("Fast", 0.05), ("Medium", 0.3), ("Slow", 0.8)):
            a = QAction(label, self, checkable=True)
            a.setChecked(abs(d - self.anim_delay) < 0.01)
            a.triggered.connect(lambda _=False, d=d: self._set_anim(d))
            speed.addAction(a)
        self.speed_actions = speed.actions()

        m = mb.addMenu("&Tools")
        m.addAction(self.a_designer)
        m.addAction(self.a_package)

        m = mb.addMenu("&View")
        for a in (self.a_dark, None, self.a_bigger, self.a_smaller):
            m.addSeparator() if a is None else m.addAction(a)
        self.view_menu = m

        m = mb.addMenu("&Help")
        m.addAction(self.a_about)

    def _build_toolbar(self):
        tb = QToolBar("Main")
        tb.setObjectName("maintoolbar")
        tb.setIconSize(QSize(20, 20))
        tb.setMovable(False)
        tb.setToolButtonStyle(Qt.ToolButtonTextBesideIcon)
        for a in (self.a_new, self.a_open, self.a_save):
            tb.addAction(a)
            tb.widgetForAction(a).setToolButtonStyle(Qt.ToolButtonIconOnly)
        tb.addSeparator()
        for a in (self.a_run, self.a_debug, self.a_stop):
            tb.addAction(a)
        tb.addSeparator()
        for a in (self.a_pause, self.a_step, self.a_over, self.a_out, self.a_animate):
            tb.addAction(a)
            tb.widgetForAction(a).setToolButtonStyle(Qt.ToolButtonIconOnly)
        tb.addSeparator()
        tb.addAction(self.a_designer)
        tb.widgetForAction(self.a_designer).setToolButtonStyle(Qt.ToolButtonTextBesideIcon)
        self.a_designer.setIconText("FreeForm")
        tb.addSeparator()
        self.label_combo = QComboBox()
        self.label_combo.setMinimumWidth(220)
        self.label_combo.setToolTip("Jump to a branch label, SUB or FUNCTION")
        self.label_combo.activated.connect(self.jump_to_label)
        tb.addWidget(QLabel("  Labels: "))
        tb.addWidget(self.label_combo)
        self.addToolBar(tb)
        self.toolbar = tb

    def _build_docks(self):
        # variables / call stack
        self.vars = QTreeWidget()
        self.vars.setHeaderLabels(["Name", "Value"])
        self.vars.header().setSectionResizeMode(0, QHeaderView.ResizeToContents)
        self.vars.itemDoubleClicked.connect(self.edit_variable)
        self.stack = QListWidget()
        self.eval_box = QLineEdit()
        self.eval_box.setPlaceholderText("Evaluate an expression while paused, e.g. len(name$) * 2")
        self.eval_box.returnPressed.connect(self.evaluate)
        self.eval_out = QLabel("")
        self.eval_out.setWordWrap(True)
        self.eval_out.setTextInteractionFlags(Qt.TextSelectableByMouse)
        w = QWidget()
        lay = QVBoxLayout(w)
        lay.setContentsMargins(4, 4, 4, 4)
        lay.addWidget(QLabel("<b>Variables</b> <span style='color:gray'>(double-click to change)</span>"))
        lay.addWidget(self.vars, 3)
        lay.addWidget(QLabel("<b>Call stack</b>"))
        lay.addWidget(self.stack, 1)
        lay.addWidget(self.eval_box)
        lay.addWidget(self.eval_out)
        self.debug_dock = QDockWidget("Debugger", self)
        self.debug_dock.setObjectName("debugdock")
        self.debug_dock.setWidget(w)
        self.addDockWidget(Qt.RightDockWidgetArea, self.debug_dock)
        self.debug_dock.hide()
        # output / problems
        self.output = QPlainTextEdit()
        self.output.setReadOnly(True)
        self.output.setMaximumBlockCount(2000)
        self.out_dock = QDockWidget("Messages", self)
        self.out_dock.setObjectName("outdock")
        self.out_dock.setWidget(self.output)
        self.addDockWidget(Qt.BottomDockWidgetArea, self.out_dock)
        self.out_dock.hide()
        self.view_menu.addSeparator()
        self.view_menu.addAction(self.debug_dock.toggleViewAction())
        self.view_menu.addAction(self.out_dock.toggleViewAction())

    # ------------------------------------------------------------- tabs/files
    def current_tab(self):
        return self.tabs.currentWidget()

    def current_editor(self):
        t = self.current_tab()
        return t.editor if t else None

    def add_tab(self, tab):
        i = self.tabs.addTab(tab, tab.title())
        self.tabs.setCurrentIndex(i)
        tab.editor.document().modificationChanged.connect(lambda _=None, t=tab: self.update_tab_title(t))
        tab.editor.textChanged.connect(lambda: self.label_timer.start(400))
        tab.editor.breakpoints_changed.connect(self.sync_breakpoints)
        tab.editor.setFocus()
        self.refresh_labels()
        return tab

    def update_tab_title(self, tab):
        i = self.tabs.indexOf(tab)
        if i >= 0:
            self.tabs.setTabText(i, tab.title())
            self.tabs.setTabToolTip(i, tab.path or "Not saved yet")
        if tab is self.current_tab():
            self.setWindowTitle(f"{tab.title()} — OpenBASIC")

    def on_tab_changed(self, i):
        t = self.current_tab()
        if t:
            self.update_tab_title(t)
        self.refresh_labels()

    def new_file(self):
        self.add_tab(EditorTab(self))

    def open_dialog(self):
        start = self.settings.value("last_dir", os.path.expanduser("~"))
        paths, _ = QFileDialog.getOpenFileNames(self, "Open program", start, FILE_FILTER)
        for p in paths:
            self.open_file(p)

    def open_file(self, path):
        path = os.path.abspath(path)
        for i in range(self.tabs.count()):
            t = self.tabs.widget(i)
            if t.path and os.path.samefile(t.path, path):
                self.tabs.setCurrentIndex(i)
                return t
        try:
            text, enc, nl = read_source(path)
        except OSError as e:
            QMessageBox.warning(self, "Can't open file", f"{path}\n\n{e.strerror}")
            return None
        # replace a pristine untitled tab
        cur = self.current_tab()
        if cur and not cur.path and not cur.editor.toPlainText() and not cur.editor.document().isModified():
            self.tabs.removeTab(self.tabs.indexOf(cur))
            cur.deleteLater()
        tab = EditorTab(self, path, text)
        tab.encoding, tab.newline = enc, nl
        self.add_tab(tab)
        self.settings.setValue("last_dir", os.path.dirname(path))
        self._add_recent(path)
        self.update_tab_title(tab)
        return tab

    def _add_recent(self, path):
        rec = [p for p in (self.settings.value("recent", []) or []) if isinstance(p, str) and p != path]
        rec.insert(0, path)
        self.settings.setValue("recent", rec[:12])

    def _fill_recent(self):
        self.recent_menu.clear()
        rec = [p for p in (self.settings.value("recent", []) or []) if isinstance(p, str)]
        if not rec:
            a = self.recent_menu.addAction("(none)")
            a.setEnabled(False)
        for p in rec:
            a = self.recent_menu.addAction(p)
            a.triggered.connect(lambda _=False, p=p: self.open_file(p))

    def _fill_examples(self):
        self.examples_menu.clear()
        if os.path.isdir(EXAMPLES_DIR):
            for f in sorted(os.listdir(EXAMPLES_DIR)):
                if f.lower().endswith(".bas"):
                    a = self.examples_menu.addAction(f[:-4].replace("_", " "))
                    a.triggered.connect(lambda _=False, f=f: self.open_file(os.path.join(EXAMPLES_DIR, f)))

    def save(self):
        t = self.current_tab()
        if not t:
            return False
        if not t.path:
            return self.save_as()
        try:
            t.save()
        except OSError as e:
            QMessageBox.warning(self, "Save failed", e.strerror or str(e))
            return False
        self.statusBar().showMessage(f"Saved {t.path}", 3000)
        return True

    def save_as(self):
        t = self.current_tab()
        if not t:
            return False
        start = t.path or os.path.join(self.settings.value("last_dir", os.path.expanduser("~")), "untitled.bas")
        path, _ = QFileDialog.getSaveFileName(self, "Save program", start, FILE_FILTER)
        if not path:
            return False
        if not os.path.splitext(path)[1]:
            path += ".bas"
        try:
            t.save(path)
        except OSError as e:
            QMessageBox.warning(self, "Save failed", e.strerror or str(e))
            return False
        self.settings.setValue("last_dir", os.path.dirname(path))
        self._add_recent(path)
        self.update_tab_title(t)
        return True

    def maybe_save(self, tab):
        if not tab.editor.document().isModified():
            return True
        r = QMessageBox.question(self, "Save changes?", f"Save changes to {tab.title().rstrip(' *')}?",
                                 QMessageBox.Save | QMessageBox.Discard | QMessageBox.Cancel)
        if r == QMessageBox.Cancel:
            return False
        if r == QMessageBox.Save:
            self.tabs.setCurrentWidget(tab)
            return self.save()
        return True

    def close_tab(self, i):
        tab = self.tabs.widget(i)
        if tab is None:
            return
        if self.running and tab is getattr(self, "run_tab", None):
            QMessageBox.information(self, "Program running", "Stop the program before closing its tab.")
            return
        if not self.maybe_save(tab):
            return
        self.tabs.removeTab(i)
        tab.deleteLater()
        if self.tabs.count() == 0:
            self.new_file()

    def closeEvent(self, ev):
        if self.running:
            self.stop()
        for i in range(self.tabs.count()):
            if not self.maybe_save(self.tabs.widget(i)):
                ev.ignore()
                return
        self.settings.setValue("session", [self.tabs.widget(i).path for i in range(self.tabs.count())
                                           if self.tabs.widget(i).path])
        self.settings.setValue("geometry", self.saveGeometry())
        if self.last_host and self.last_host.console:
            self.last_host.console.close()
        ev.accept()
        QApplication.instance().quit()

    def dragEnterEvent(self, ev):
        if ev.mimeData().hasUrls():
            ev.acceptProposedAction()

    def dropEvent(self, ev):
        for u in ev.mimeData().urls():
            if u.isLocalFile():
                self.open_file(u.toLocalFile())

    # ------------------------------------------------------------- editing
    def refresh_labels(self):
        ed = self.current_editor()
        self.label_combo.clear()
        if not ed:
            return
        for name, line in ed.labels():
            self.label_combo.addItem(name, line)

    def jump_to_label(self, i):
        line = self.label_combo.itemData(i)
        ed = self.current_editor()
        if ed and line:
            ed.goto_line(line)
            ed.setFocus()

    def goto_line(self):
        ed = self.current_editor()
        n, ok = QInputDialog.getInt(self, "Go to line", "Line number:", ed.textCursor().blockNumber() + 1,
                                    1, ed.blockCount())
        if ok:
            ed.goto_line(n)

    def change_font(self, delta):
        self.font_size = max(7, min(32, self.font_size + delta))
        self.settings.setValue("font_size", self.font_size)
        for i in range(self.tabs.count()):
            self.tabs.widget(i).editor.set_font_size(self.font_size)

    def toggle_theme(self):
        name = "dark" if self.a_dark.isChecked() else "light"
        theme.apply(name)
        self.settings.setValue("theme", name)
        for i in range(self.tabs.count()):
            self.tabs.widget(i).editor.apply_theme()
        icons.clear_cache()
        self._refresh_icons()

    def _refresh_icons(self):
        for a, name in ((self.a_new, "new"), (self.a_open, "open"), (self.a_save, "save"), (self.a_run, "run"),
                        (self.a_debug, "debug"), (self.a_stop, "stop"), (self.a_pause, "pause"),
                        (self.a_step, "step_into"), (self.a_over, "step_over"), (self.a_out, "step_out"),
                        (self.a_animate, "animate"), (self.a_designer, "designer"), (self.a_find, "find"),
                        (self.a_bp, "breakpoint"), (self.a_check, "check"), (self.a_package, "package")):
            a.setIcon(icons.icon(name))

    def _set_anim(self, d):
        self.anim_delay = d
        self.settings.setValue("anim_delay", d)
        for a in self.speed_actions:
            a.setChecked(a.text() == {0.05: "Fast", 0.3: "Medium", 0.8: "Slow"}[d])

    def about(self):
        QMessageBox.about(self, "About OpenBASIC",
                          f"<h3>OpenBASIC {__version__}</h3>"
                          "<p>An open source, cross-platform IDE that runs Just BASIC and "
                          "Liberty BASIC style programs on Windows, macOS and Linux.</p>"
                          "<p>Released under the MIT License.</p>"
                          "<p>Just BASIC and Liberty BASIC are products of Shoptalk Systems. "
                          "OpenBASIC is an independent project and is not affiliated with them.</p>")

    # ------------------------------------------------------------- run / debug
    def log(self, text):
        self.output.appendPlainText(text)

    def update_actions(self):
        r, p = self.running, self.paused
        self.a_run.setEnabled(not r or p)
        self.a_run.setText("&Continue" if (r and p) else "&Run")
        self.a_run.setToolTip("Continue (F5)" if (r and p) else "Run (F5)")
        self.a_debug.setEnabled(not r)
        self.a_stop.setEnabled(r)
        dbg = r and self.debugger is not None
        self.a_pause.setEnabled(dbg and not p)
        for a in (self.a_step, self.a_over, self.a_out):
            a.setEnabled((dbg and p) or not r)
        self.a_animate.setEnabled(not r or (dbg and p))
        self.a_package.setEnabled(not r)

    def run_clicked(self):
        if self.running and self.paused:
            self.step("run")
        elif not self.running:
            self.start_run(debug=bool(self.current_editor() and self.current_editor().breakpoints))

    def sync_breakpoints(self):
        if self.debugger is not None and self.current_tab() is getattr(self, "run_tab", None):
            self.debugger.breakpoints = set(self.run_tab.editor.breakpoints)

    def clear_breakpoints(self):
        ed = self.current_editor()
        if ed:
            ed.set_breakpoints(set())

    def start_run(self, debug=False, step_first=False, mode=None):
        if self.running:
            return
        tab = self.current_tab()
        if tab is None:
            return
        if tab.path and tab.editor.document().isModified() and self.settings.value("autosave", "true") == "true":
            try:
                tab.save()
            except OSError:
                pass
        self.run_tab = tab
        self.running = True
        self.paused = False
        if debug or mode:
            self.debugger = Debugger()
            self.debugger.breakpoints = set(tab.editor.breakpoints)
            self.debugger.mode = mode or ("step" if step_first else "run")
            self.debug_dock.show()
        else:
            self.debugger = None
        tab.editor.set_error_line(None)
        tab.editor.set_exec_line(None)
        if self.last_host and self.last_host.console:
            self.last_host.console.close()
            self.last_host.console.deleteLater()
            self.last_host.console = None
        self.update_actions()
        self.statusBar().showMessage("Running…")
        QTimer.singleShot(0, lambda: self._run_now(tab))

    def _default_dir(self):
        d = os.path.join(os.path.expanduser("~"), "OpenBASIC")
        os.makedirs(d, exist_ok=True)
        return d

    def _run_now(self, tab):
        from ..runtime.runner import run_program
        src = tab.editor.toPlainText()
        path = tab.path or os.path.join(self._default_dir(), "untitled.bas")
        tab.editor.setReadOnly(self.debugger is not None)

        def ready(host, interp):
            self.host, self.interp = host, interp

        app = QApplication.instance()
        app.setQuitOnLastWindowClosed(False)
        result, host = run_program(app, src, path, debug_ui=self, debugger=self.debugger, host_ready=ready)
        self.last_host = host
        self.host = None
        self.interp = None
        self.running = False
        self.paused = False
        self.debugger = None
        try:
            tab.editor.setReadOnly(False)
            tab.editor.set_exec_line(None)
        except RuntimeError:
            return  # tab was closed
        self.vars.clear()
        self.stack.clear()
        name = os.path.basename(path)
        if result.status == "ended":
            self.statusBar().showMessage(f"{name} finished", 6000)
        elif result.status == "stopped":
            self.statusBar().showMessage(f"{name} stopped", 6000)
        else:
            kind = "Syntax error" if result.status == "syntax" else "Runtime error"
            where = f" on line {result.line}" if result.line else ""
            msg = f"{kind}{where}: {result.error}"
            self.log(f"{name}: {msg}")
            self.out_dock.show()
            if result.line:
                self.tabs.setCurrentWidget(tab)
                tab.editor.set_error_line(result.line)
            self.statusBar().showMessage(msg)
            box = QMessageBox(QMessageBox.Warning, kind, f"<b>{kind}{where}</b><br><br>{_html(result.error)}",
                              QMessageBox.Ok, self)
            box.exec()
        if host.console is not None and host.console.isVisible():
            host.console.setWindowTitle(f"{name} - OpenBASIC (finished)")
        self.update_actions()
        self.activateWindow()

    def stop(self):
        if self.host is not None:
            self.host.request_stop()
        elif self.running:
            self.running = False
            self.update_actions()

    def pause(self):
        if self.debugger is not None:
            self.debugger.pause_requested = True
            self.statusBar().showMessage("Pausing… (a program waiting for events pauses after the next event)")

    def step(self, mode):
        if not self.running:
            # start a debug session in the requested mode
            self.start_run(debug=True, step_first=(mode in ("step", "over", "out")),
                           mode=("animate" if mode == "animate" else None))
            return
        if self.debugger is None or self.interp is None:
            return
        d = self.debugger
        d.mode = mode
        d.target_depth = self.interp.depth()
        self.paused = False
        self.update_actions()
        self.statusBar().showMessage("Running…" if mode != "animate" else "Animating…")
        if self.host:
            self.host.debug_resume()

    # debugger callbacks from the host
    def on_debug_pause(self, interp, fr, line):
        self.paused = True
        self.paused_frame = fr
        self.tabs.setCurrentWidget(self.run_tab)
        self.run_tab.editor.set_exec_line(line)
        self.fill_debug(interp, fr)
        self.update_actions()
        where = f" in {fr.unit.kind.upper()} {fr.unit.name}" if fr.unit.kind != "main" else ""
        self.statusBar().showMessage(f"Paused at line {line}{where} — F8 step, F10 step over, F5 continue")
        self.raise_()
        self.activateWindow()

    def on_debug_resume(self):
        self.paused = False
        self.paused_frame = None
        try:
            self.run_tab.editor.set_exec_line(None)
        except RuntimeError:
            pass
        self.update_actions()

    def on_debug_line(self, interp, fr, line):
        self.run_tab.editor.set_exec_line(line)
        self.fill_debug(interp, fr)

    def animate_delay(self):
        return self.anim_delay

    def fill_debug(self, interp, fr):
        expanded = {self.vars.topLevelItem(i).text(0): self.vars.topLevelItem(i).isExpanded()
                    for i in range(self.vars.topLevelItemCount())}
        self.vars.clear()
        glob, local = interp.snapshot_vars(fr)

        def add_group(title, items, expand=True):
            g = QTreeWidgetItem([title, ""])
            f = g.font(0)
            f.setBold(True)
            g.setFont(0, f)
            self.vars.addTopLevelItem(g)
            for k in sorted(items, key=str.lower):
                v = items[k]
                it = QTreeWidgetItem([k, _show(v)])
                it.setData(0, Qt.UserRole, ("var", k))
                g.addChild(it)
            g.setExpanded(expanded.get(title, expand))
            return g
        if fr.unit.kind != "main":
            add_group(f"Locals ({fr.unit.name})", local)
        from ..interp import SYSVARS
        user = {k: v for k, v in glob.items() if k not in SYSVARS}
        system = {k: v for k, v in glob.items() if k in SYSVARS}
        add_group("Variables", user)
        if interp.arrays:
            g = QTreeWidgetItem(["Arrays", ""])
            self.vars.addTopLevelItem(g)
            for name in sorted(interp.arrays, key=str.lower):
                a = interp.arrays[name]
                dims = ", ".join(str(d - 1) for d in a.dims)
                ai = QTreeWidgetItem([f"{name}({dims})", ""])
                g.addChild(ai)
                shown = 0
                if len(a.dims) == 1:
                    for i, v in enumerate(a.data):
                        if v not in ("", 0) and shown < 200:
                            ai.addChild(QTreeWidgetItem([f"{name}({i})", _show(v)]))
                            shown += 1
                else:
                    w = a.dims[1]
                    for i, v in enumerate(a.data):
                        if v not in ("", 0) and shown < 200:
                            ai.addChild(QTreeWidgetItem([f"{name}({i // w}, {i % w})", _show(v)]))
                            shown += 1
                ai.setText(1, f"{shown} set item(s)" if shown < 200 else "200+ set items")
            g.setExpanded(expanded.get("Arrays", False))
        add_group("System", system, expand=False)
        self.stack.clear()
        for name, gos in reversed(interp.call_stack()):
            self.stack.addItem(name + (f"   (inside {gos} GOSUB{'s' if gos > 1 else ''})" if gos else ""))

    def edit_variable(self, item, col):
        data = item.data(0, Qt.UserRole)
        if not data or not self.paused or self.interp is None:
            return
        name = data[1]
        cur = item.text(1)
        text, ok = QInputDialog.getText(self, "Change variable", f"New value for {name}:",
                                        text=cur.strip('"') if name.endswith("$") else cur)
        if ok:
            from ..values import val
            v = text if name.endswith("$") else val(text)
            self.interp.set_var_dynamic(self.paused_frame, name, v)
            self.fill_debug(self.interp, self.paused_frame)

    def evaluate(self):
        expr = self.eval_box.text().strip()
        if not expr:
            return
        if not (self.paused and self.interp):
            self.eval_out.setText("Pause the program first (F7 to debug, or a breakpoint).")
            return
        from ..builtins import _eval_impl
        try:
            v = _eval_impl(self.interp, self.paused_frame, expr)
            self.eval_out.setText(f"{expr} = {_show(v)}")
        except BasicError as e:
            self.eval_out.setText(f"Error: {e.msg}")

    def check_syntax(self):
        ed = self.current_editor()
        if not ed:
            return
        try:
            Interpreter(ed.toPlainText(), Host(), self.current_tab().path)
        except BasicError as e:
            ed.set_error_line(e.line)
            self.statusBar().showMessage(f"Line {e.line}: {e.msg}")
            self.log(f"Syntax check: line {e.line}: {e.msg}")
            self.out_dock.show()
            return
        ed.set_error_line(None)
        self.statusBar().showMessage("No syntax errors found", 5000)

    # ------------------------------------------------------------- tools
    def open_designer(self):
        from .designer import DesignerWindow
        self.designer = DesignerWindow(self)
        ed = self.current_editor()
        if ed and ed.textCursor().hasSelection():
            self.designer.import_code(ed.textCursor().selectedText().replace("\u2029", "\n"))
        self.designer.show()

    def insert_code(self, code, new_tab=False):
        if new_tab:
            self.add_tab(EditorTab(self, None, code))
            self.current_tab().editor.document().setModified(True)
            return
        ed = self.current_editor()
        c = ed.textCursor()
        c.insertText(code)
        ed.setFocus()
        self.activateWindow()

    def open_packager(self):
        tab = self.current_tab()
        if tab is None:
            return
        if not tab.path or tab.editor.document().isModified():
            QMessageBox.information(self, "Save first", "Save the program before making a standalone app.")
            if not self.save():
                return
        from .packager import PackagerDialog
        dlg = PackagerDialog(self, tab.path)
        dlg.exec()


def _show(v):
    if isinstance(v, str):
        s = v if len(v) < 200 else v[:200] + "…"
        return '"' + s.replace("\r", "\\r").replace("\n", "\\n") + '"'
    return to_str(v)


def _html(s):
    return (s or "").replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")

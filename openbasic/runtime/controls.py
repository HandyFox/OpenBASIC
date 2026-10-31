"""Window controls: buttons, textboxes, listboxes and friends."""
from PySide6.QtCore import Qt, QSize
from PySide6.QtGui import QColor, QIcon, QPixmap, QTextCursor, QFontMetrics
from PySide6.QtWidgets import (QCheckBox, QComboBox, QGroupBox, QLabel, QLineEdit, QListWidget,
                               QPlainTextEdit, QPushButton, QRadioButton, QToolButton, QAbstractItemView)

from ..errors import BasicError
from .graphics import GraphicsView
from .style import css_color, parse_color, parse_font


def _words(cmd):
    return cmd.split()


def common_cmd(widget, op, args, host=None):
    """Commands every control understands. Returns True when handled."""
    if op == "enable":
        widget.setEnabled(True)
    elif op == "disable":
        widget.setEnabled(False)
    elif op == "show":
        widget.show()
    elif op == "hide":
        widget.hide()
    elif op == "setfocus":
        widget.setFocus()
        widget.window().activateWindow()
    elif op == "font":
        widget.setFont(parse_font(" ".join(args)))
    elif op == "locate":
        try:
            x, y, w, h = (int(float(a)) for a in args[:4])
        except ValueError:
            raise BasicError("locate needs x, y, width and height")
        widget.setGeometry(x, y, w, h)
    elif op == "refresh":
        widget.update()
    else:
        return False
    return True


def text_edit_command(edit, cmd, lookup, newline):
    """Commands shared by texteditor controls and text windows."""
    if not cmd.startswith("!"):
        c = edit.textCursor()
        c.movePosition(QTextCursor.End)
        c.insertText(cmd + ("\n" if newline else ""))
        edit.setTextCursor(c)
        edit.ensureCursorVisible()
        return None
    words = cmd[1:].split()
    if not words:
        return None
    op = words[0].lower()
    args = words[1:]
    if op == "cls":
        edit.clear()
    elif op == "contents?":
        return {args[0]: edit.toPlainText()} if args else None
    elif op == "contents":
        if args:
            v = lookup(args[0]) if lookup else ""
            edit.setPlainText(v if isinstance(v, str) else str(v))
    elif op == "selection?":
        return {args[0]: edit.textCursor().selectedText().replace(" ", "\n")} if args else None
    elif op == "selectall":
        edit.selectAll()
    elif op == "copy":
        edit.copy()
    elif op == "cut":
        edit.cut()
    elif op == "paste":
        edit.paste()
    elif op == "line":
        if len(args) >= 2:
            n = int(float(args[0]))
            block = edit.document().findBlockByNumber(n - 1)
            return {args[1]: block.text() if block.isValid() else ""}
    elif op == "lines":
        return {args[0]: edit.document().blockCount()} if args else None
    elif op == "modified?":
        return {args[0]: "true" if edit.document().isModified() else "false"} if args else None
    elif op == "origin?":
        first = edit.firstVisibleBlock().blockNumber() + 1
        out = {}
        if args:
            out[args[0]] = first
        if len(args) > 1:
            out[args[1]] = edit.horizontalScrollBar().value() + 1
        return out
    elif op == "origin":
        if args:
            block = edit.document().findBlockByNumber(int(float(args[0])) - 1)
            if block.isValid():
                c = QTextCursor(block)
                edit.setTextCursor(c)
                edit.ensureCursorVisible()
    elif op == "insert":
        if args:
            v = lookup(args[0]) if lookup else " ".join(args)
            edit.insertPlainText(v if isinstance(v, str) else str(v))
    elif op in ("autoresize", "trapclose"):
        pass
    elif common_cmd(edit, op, args):
        pass
    else:
        raise BasicError(f"Unknown text command '!{words[0]}'")
    return None


class Control:
    def __init__(self, host, win, key, spec, parent):
        self.host = host
        self.win = win
        self.key = key
        self.spec = spec
        self.widget = None
        self.corner = spec.get("corner", "ul")

    def fire(self, handler):
        if handler:
            self.host.push_event(handler, [self.key], {}, self.key)

    def geometry_from_spec(self, default_w=100, default_h=25):
        s = self.spec
        w = s.get("w") or default_w
        h = s.get("h") or default_h
        return s.get("x", 0), s.get("y", 0), w, h

    def command(self, text, lookup, newline):
        cmd = text.strip()
        if cmd.startswith("!"):
            cmd = cmd[1:]
        words = cmd.split()
        if not words:
            return None
        op = words[0].lower()
        if common_cmd(self.widget, op, words[1:], self.host):
            return None
        return self.other(op, words[1:], cmd)

    def other(self, op, args, cmd):
        raise BasicError(f"Unknown command '{cmd}' for {self.key}")


class ButtonControl(Control):
    def __init__(self, host, win, key, spec, parent):
        super().__init__(host, win, key, spec, parent)
        text = spec.get("text", "")
        b = QPushButton(parent)
        b.setAutoDefault(False)
        b.clicked.connect(lambda: self.fire(spec.get("handler")))
        self.widget = b
        img = None
        if text.lower().endswith(".bmp"):
            # Just BASIC: a button whose label is a .bmp file shows the picture
            import os
            path = host.resolve_path(text)
            if os.path.exists(path):
                img = host.load_image_file(path)
        if img is not None:
            from PySide6.QtGui import QIcon, QPixmap
            b.setIcon(QIcon(QPixmap.fromImage(img)))
            b.setIconSize(img.size())
            self.rect = self.geometry_from_spec(img.width() + 6, img.height() + 6)
        else:
            b.setText(text)
            fm = QFontMetrics(b.font())
            dw = max(22, fm.horizontalAdvance(text.replace("&", "")) + 12)
            self.rect = self.geometry_from_spec(dw, max(24, fm.height() + 10))

    def command(self, text, lookup, newline):
        if not text.startswith("!"):
            self.widget.setText(text)
            return None
        return super().command(text, lookup, newline)

    def other(self, op, args, cmd):
        if op == "label":
            self.widget.setText(" ".join(args))
            return None
        if op == "setfocus":
            self.widget.setFocus()
            return None
        raise BasicError(f"Unknown button command '!{cmd}'")


class BmpButtonControl(Control):
    def __init__(self, host, win, key, spec, parent):
        super().__init__(host, win, key, spec, parent)
        b = QToolButton(parent)
        img = host.load_image_file(spec["file"])
        self._set_image(b, img)
        b.clicked.connect(lambda: self.fire(spec.get("handler")))
        self.widget = b
        self.rect = (spec.get("x", 0), spec.get("y", 0), img.width() + 4, img.height() + 4)

    @staticmethod
    def _set_image(b, img):
        b.setIcon(QIcon(QPixmap.fromImage(img)))
        b.setIconSize(img.size())
        b.setToolButtonStyle(Qt.ToolButtonIconOnly)

    def other(self, op, args, cmd):
        if op == "bitmap" and args:
            img = self.host.get_bitmap(args[0])
            self._set_image(self.widget, img)
            return None
        raise BasicError(f"Unknown bmpbutton command '{cmd}'")


class TextboxControl(Control):
    def __init__(self, host, win, key, spec, parent):
        super().__init__(host, win, key, spec, parent)
        self.widget = QLineEdit(parent)
        self.rect = self.geometry_from_spec(100, 25)

    def command(self, text, lookup, newline):
        if not text.startswith("!"):
            self.widget.setText(text)
            return None
        return super().command(text, lookup, newline)

    def other(self, op, args, cmd):
        w = self.widget
        if op == "contents?":
            return {args[0]: w.text()} if args else None
        if op == "contents":
            if args:
                v = self.host.lookup(args[0])
                w.setText(v if isinstance(v, str) else str(v))
            return None
        if op == "selection?":
            return {args[0]: w.selectedText()} if args else None
        if op == "selectall":
            w.selectAll()
        elif op == "copy":
            w.copy()
        elif op == "cut":
            w.cut()
        elif op == "paste":
            w.paste()
        elif op == "cls":
            w.clear()
        else:
            raise BasicError(f"Unknown textbox command '!{cmd}'")
        return None


class TextEditorControl(Control):
    def __init__(self, host, win, key, spec, parent):
        super().__init__(host, win, key, spec, parent)
        self.widget = QPlainTextEdit(parent)
        self.rect = self.geometry_from_spec(200, 100)

    def command(self, text, lookup, newline):
        return text_edit_command(self.widget, text, self.host.lookup, newline)


class StaticTextControl(Control):
    def __init__(self, host, win, key, spec, parent):
        super().__init__(host, win, key, spec, parent)
        lab = QLabel(spec.get("text", ""), parent)
        lab.setAlignment(Qt.AlignLeft | Qt.AlignTop)
        lab.setTextFormat(Qt.PlainText)
        self.widget = lab
        fm = QFontMetrics(lab.font())
        self.rect = self.geometry_from_spec(fm.horizontalAdvance(lab.text()) + 4, fm.height() + 4)
        self.update_wrap()

    def update_wrap(self):
        lab = self.widget
        fm = QFontMetrics(lab.font())
        # wrap only when there is room for more than one line, like Windows does
        lab.setWordWrap(self.rect[3] >= fm.lineSpacing() * 2 or "\n" in lab.text())

    def command(self, text, lookup, newline):
        if text.startswith("!"):
            words = text[1:].split()
            if words and words[0].lower() in ("enable", "disable", "show", "hide", "font", "locate",
                                              "setfocus", "refresh"):
                r = super().command(text, lookup, newline)
                self.update_wrap()
                return r
        self.widget.setText(text)
        self.update_wrap()
        return None


class GroupboxControl(Control):
    def __init__(self, host, win, key, spec, parent):
        super().__init__(host, win, key, spec, parent)
        self.widget = QGroupBox(spec.get("text", ""), parent)
        self.widget.setAttribute(Qt.WA_TransparentForMouseEvents)
        self.rect = self.geometry_from_spec(150, 100)

    def command(self, text, lookup, newline):
        if text.startswith("!"):
            return super().command(text, lookup, newline)
        self.widget.setTitle(text)
        return None


class ListboxControl(Control):
    def __init__(self, host, win, key, spec, parent):
        super().__init__(host, win, key, spec, parent)
        lb = QListWidget(parent)
        lb.setSelectionMode(QAbstractItemView.SingleSelection)
        lb.addItems(spec["items"]())
        lb.itemDoubleClicked.connect(lambda _: self.fire(spec.get("handler")))
        lb.itemActivated.connect(lambda _: None)
        self.single = None
        lb.itemClicked.connect(self._clicked)
        self.widget = lb
        self.rect = self.geometry_from_spec(150, 100)

    def _clicked(self, _):
        if self.single is not None:
            self.fire(self.single or self.spec.get("handler"))

    def other(self, op, args, cmd):
        lb = self.widget
        if op == "reload":
            sel = lb.currentRow()
            lb.clear()
            lb.addItems(self.spec["items"]())
            if 0 <= sel < lb.count():
                lb.setCurrentRow(sel)
        elif op == "select":
            text = " ".join(args)
            items = lb.findItems(text, Qt.MatchExactly)
            if items:
                lb.setCurrentItem(items[0])
            else:
                lb.clearSelection()
        elif op == "selectindex":
            i = int(float(args[0])) if args else 0
            if 1 <= i <= lb.count():
                lb.setCurrentRow(i - 1)
            else:
                lb.clearSelection()
                lb.setCurrentRow(-1)
        elif op == "selection?":
            item = lb.currentItem() if lb.selectedItems() else None
            return {args[0]: item.text() if item else ""} if args else None
        elif op == "selectindex?":
            return {args[0]: (lb.currentRow() + 1) if lb.selectedItems() else 0} if args else None
        elif op == "singleclickselect":
            h = args[0] if args else None
            if h:
                self.single = ("label", h.strip("[]").lower()) if h.startswith("[") else ("sub", h)
            else:
                self.single = False
        elif op == "doubleclickselect":
            self.single = None
        elif op == "horizscrollbar":
            pass
        else:
            raise BasicError(f"Unknown listbox command '{cmd}'")
        return None


class ComboboxControl(Control):
    def __init__(self, host, win, key, spec, parent):
        super().__init__(host, win, key, spec, parent)
        cb = QComboBox(parent)
        cb.setEditable(True)
        cb.setInsertPolicy(QComboBox.NoInsert)
        cb.addItems(spec["items"]())
        cb.setCurrentIndex(-1)
        cb.activated.connect(lambda _: self.fire(spec.get("handler")))
        self.widget = cb
        # Just BASIC's height is the drop-down list's height; the box itself is one line
        x, y, w, h = self.geometry_from_spec(150, 100)
        fm = QFontMetrics(cb.font())
        cb.setMaxVisibleItems(max(3, h // max(1, fm.lineSpacing() + 4)))
        self.rect = (x, y, w, max(22, cb.sizeHint().height()))

    def other(self, op, args, cmd):
        cb = self.widget
        if op == "reload":
            text = cb.currentText()
            cb.clear()
            cb.addItems(self.spec["items"]())
            cb.setCurrentIndex(-1)
            cb.setEditText(text)
        elif op == "select":
            text = " ".join(args)
            i = cb.findText(text)
            cb.setCurrentIndex(i)
            if i < 0:
                cb.setEditText(text)
        elif op == "selectindex":
            i = int(float(args[0])) if args else 0
            cb.setCurrentIndex(i - 1 if 1 <= i <= cb.count() else -1)
        elif op in ("selection?", "contents?"):
            return {args[0]: cb.currentText()} if args else None
        elif op == "selectindex?":
            i = cb.findText(cb.currentText())
            return {args[0]: i + 1 if i >= 0 else 0} if args else None
        elif op == "!text" or op == "text":
            cb.setEditText(" ".join(args))
        else:
            raise BasicError(f"Unknown combobox command '{cmd}'")
        return None


class CheckControl(Control):
    def __init__(self, host, win, key, spec, parent, radio=False):
        super().__init__(host, win, key, spec, parent)
        w = (QRadioButton if radio else QCheckBox)(spec.get("text", ""), parent)
        w.clicked.connect(self._clicked)
        self.widget = w
        fm = QFontMetrics(w.font())
        self.rect = self.geometry_from_spec(fm.horizontalAdvance(w.text()) + 30, max(20, fm.height() + 4))

    def _clicked(self, checked):
        self.fire(self.spec.get("set") if checked else self.spec.get("reset"))

    def other(self, op, args, cmd):
        w = self.widget
        if op == "set":
            w.setChecked(True)
        elif op == "reset":
            w.setChecked(False)
        elif op == "value?":
            return {args[0]: "set" if w.isChecked() else "reset"} if args else None
        else:
            raise BasicError(f"Unknown {self.spec['type']} command '{cmd}'")
        return None

    def command(self, text, lookup, newline):
        cmd = text.strip().lstrip("!")
        words = cmd.split()
        if words and words[0].lower() in ("set", "reset", "value?", "enable", "disable", "show", "hide",
                                          "font", "locate", "setfocus", "refresh"):
            return super().command(text, lookup, newline)
        if words and words[0].lower() == "label":
            self.widget.setText(" ".join(words[1:]))
            return None
        self.widget.setText(text)
        return None


class GraphicboxControl(Control):
    def __init__(self, host, win, key, spec, parent):
        super().__init__(host, win, key, spec, parent)
        x, y, w, h = self.geometry_from_spec(200, 150)
        self.widget = GraphicsView(host, key, parent, w, h)
        self.rect = (x, y, w, h)

    def command(self, text, lookup, newline):
        return self.widget.command(text, lookup)


CONTROL_CLASSES = {
    "button": ButtonControl,
    "bmpbutton": BmpButtonControl,
    "textbox": TextboxControl,
    "texteditor": TextEditorControl,
    "statictext": StaticTextControl,
    "groupbox": GroupboxControl,
    "listbox": ListboxControl,
    "combobox": ComboboxControl,
    "checkbox": lambda *a: CheckControl(*a, radio=False),
    "radiobutton": lambda *a: CheckControl(*a, radio=True),
    "graphicbox": GraphicboxControl,
}


def apply_colors(ctl, settings):
    """Apply TextboxColor$ and friends."""
    t = ctl.spec["type"]
    w = ctl.widget
    styles = []
    fg = settings.get("fg")
    try:
        if t == "textbox" and settings.get("textbox"):
            styles.append(f"background-color: {css_color(parse_color(settings['textbox']))};")
        elif t == "texteditor" and settings.get("texteditor"):
            styles.append(f"background-color: {css_color(parse_color(settings['texteditor']))};")
        elif t == "listbox" and settings.get("listbox"):
            styles.append(f"background-color: {css_color(parse_color(settings['listbox']))};")
        elif t == "combobox" and settings.get("combobox"):
            styles.append(f"background-color: {css_color(parse_color(settings['combobox']))};")
        if fg and t in ("statictext", "checkbox", "radiobutton", "groupbox"):
            styles.append(f"color: {css_color(parse_color(fg))};")
    except BasicError:
        return
    if styles:
        w.setStyleSheet(" ".join(styles))

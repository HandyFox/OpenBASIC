"""The code editor: syntax highlighting, line numbers, breakpoints."""
import re

from PySide6.QtCore import QRect, QRegularExpression, QSize, Qt, Signal
from PySide6.QtGui import (QColor, QFont, QFontDatabase, QKeySequence, QPainter, QSyntaxHighlighter,
                           QTextBlockUserData, QTextCharFormat, QTextCursor, QTextFormat)
from PySide6.QtWidgets import QPlainTextEdit, QTextEdit, QWidget

from . import theme

KEYWORDS = """
and as byref call case close confirm data dim do else elseif end endif exit filedialog files for function
gosub global goto if input kill let line loop mod name next nomainwin not notice open or print prompt
read redim restore return run scan select step stop sub then timer to until wait wend while xor
beep cls colordialog fontdialog loadbmp unloadbmp playwave playmidi stopmidi sort locate seek get put
gettrim field trace cursor maphandle calldll popupmenu randomize lprint len
button bmpbutton textbox texteditor statictext groupbox listbox combobox checkbox radiobutton graphicbox menu
window window_nf window_popup dialog dialog_modal dialog_nf dialog_nf_modal dialog_fs dialog_popup graphics
graphics_nf_nsb graphics_nsb graphics_fs graphics_fs_nsb graphics_nf text text_nf text_fs text_nsb append
output random binary dll ul ur ll lr
""".split()

FUNCTIONS = """
abs acs asn atn cos sin tan exp log sqr int rnd val str$ left$ right$ mid$ instr upper$ lower$ trim$
space$ chr$ asc date$ time$ eof lof loc input$ word$ using tab min max hexdec dechex$ eval eval$
mkdir rmdir midipos hwnd sgn
""".split()

SYSVARS = """WindowWidth WindowHeight UpperLeftX UpperLeftY DisplayWidth DisplayHeight DefaultDir$
StartupDir$ Platform$ Version$ Drives$ CommandLine$ Inkey$ MouseX MouseY BackgroundColor$
ForegroundColor$ TextboxColor$ ListboxColor$ ComboboxColor$ TexteditorColor$""".split()

GUI_COMMANDS = """trapclose font setfocus contents? selection? selectindex? value? reload select selectindex
set reset enable disable show hide locate cls fill color backcolor size down up goto place line box boxfilled
circle circlefilled ellipse ellipsefilled pie piefilled north turn go home posxy flush discard redraw
when getbmp drawbmp bmpsave background addsprite spritexy spritexy? drawsprites spritemovexy spritetravelxy
spritevisible spritescale spriteorient spriteoffset centersprite cyclesprite spritecollides removesprite
spriteimage spritetofront spritetoback copy paste cut selectall leftButtonDown leftButtonUp leftButtonMove
leftButtonDouble rightButtonDown rightButtonUp mouseMove characterInput""".split()


class Highlighter(QSyntaxHighlighter):
    def __init__(self, doc):
        super().__init__(doc)
        self.rules = []
        self.formats = {}
        kw = "|".join(re.escape(k) for k in sorted(KEYWORDS, key=len, reverse=True))
        fn = "|".join(re.escape(k) for k in sorted(FUNCTIONS, key=len, reverse=True))
        sv = "|".join(re.escape(k) for k in SYSVARS)
        self.rules = [
            (QRegularExpression(r"\b(?:%s)(?=\s*\()" % fn, QRegularExpression.CaseInsensitiveOption), "func"),
            (QRegularExpression(r"(?<![\w.$])(?:%s)(?![\w.$])" % kw, QRegularExpression.CaseInsensitiveOption), "keyword"),
            (QRegularExpression(r"\b(?:%s)(?![\w$])" % sv.replace("$", r"\$"), QRegularExpression.CaseInsensitiveOption), "func"),
            (QRegularExpression(r"\b\d+\.?\d*(?:[eE][+-]?\d+)?\b|&[hH][0-9A-Fa-f]+"), "number"),
            (QRegularExpression(r"#[A-Za-z0-9_.]+\$?"), "handle"),
            (QRegularExpression(r"\[[^\]\s]+\]"), "label"),
        ]
        self.str_re = QRegularExpression(r'"[^"]*"?')
        self.cmd_re = QRegularExpression(r'^"!?[A-Za-z]+\??')
        self.gui_words = {w.lower().rstrip("?") for w in GUI_COMMANDS}
        self.refresh_formats()

    def refresh_formats(self):
        t = theme.current
        def fmt(color, bold=False, italic=False):
            f = QTextCharFormat()
            f.setForeground(QColor(color))
            if bold:
                f.setFontWeight(QFont.DemiBold)
            if italic:
                f.setFontItalic(True)
            return f
        self.formats = {
            "keyword": fmt(t["syn_keyword"], bold=True),
            "func": fmt(t["syn_func"]),
            "number": fmt(t["syn_number"]),
            "handle": fmt(t["syn_handle"]),
            "label": fmt(t["syn_label"], bold=True),
            "string": fmt(t["syn_string"]),
            "comment": fmt(t["syn_comment"], italic=True),
            "command": fmt(t["syn_command"]),
        }
        self.rehighlight()

    def highlightBlock(self, text):
        # find strings and comments first (a ' inside a string isn't a comment)
        spans = []
        i = 0
        n = len(text)
        comment_at = None
        while i < n:
            c = text[i]
            if c == '"':
                j = text.find('"', i + 1)
                j = n if j < 0 else j + 1
                spans.append((i, j))
                i = j
                continue
            if c == "'":
                comment_at = i
                break
            if text[i:i + 3].lower() == "rem" and (i + 3 >= n or not (text[i + 3].isalnum() or text[i + 3] in "$._")):
                before = text[:i].rstrip()
                if before == "" or before.endswith(":") or (before.endswith("]") and before.lstrip().startswith("[")):
                    comment_at = i
                    break
            i += 1
        end = comment_at if comment_at is not None else n
        for rx, kind in self.rules:
            it = rx.globalMatch(text[:end])
            while it.hasNext():
                m = it.next()
                s = m.capturedStart()
                if any(a <= s < b for a, b in spans):
                    continue
                self.setFormat(s, m.capturedLength(), self.formats[kind])
        for a, b in spans:
            self.setFormat(a, b - a, self.formats["string"])
            # colour the command word in GUI strings like "!contents? a$"
            m = self.cmd_re.match(text[a:b])
            if m.hasMatch():
                word = m.captured(0).lstrip('"!').rstrip("?").lower()
                if word in self.gui_words:
                    self.setFormat(a + 1, m.capturedLength() - 1, self.formats["command"])
        if comment_at is not None:
            self.setFormat(comment_at, n - comment_at, self.formats["comment"])


class BreakpointMark(QTextBlockUserData):
    """Attached to a line's text block so the breakpoint moves with the line."""


class Gutter(QWidget):
    def __init__(self, editor):
        super().__init__(editor)
        self.editor = editor
        self.setCursor(Qt.PointingHandCursor)

    def sizeHint(self):
        return QSize(self.editor.gutter_width(), 0)

    def paintEvent(self, ev):
        self.editor.paint_gutter(ev)

    def mousePressEvent(self, ev):
        y = ev.position().y()
        b = self.editor.firstVisibleBlock()
        top = self.editor.blockBoundingGeometry(b).translated(self.editor.contentOffset()).top()
        while b.isValid():
            h = self.editor.blockBoundingRect(b).height()
            if top <= y < top + h:
                self.editor.toggle_breakpoint(b.blockNumber() + 1)
                break
            top += h
            b = b.next()


class CodeEditor(QPlainTextEdit):
    breakpoints_changed = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.exec_line = None
        self.error_line = None
        self.gutter = Gutter(self)
        self.highlighter = Highlighter(self.document())
        f = QFontDatabase.systemFont(QFontDatabase.FixedFont)
        f.setPointSize(11)
        self.setFont(f)
        self.setLineWrapMode(QPlainTextEdit.NoWrap)
        self.setTabStopDistance(self.fontMetrics().horizontalAdvance(" ") * 4)
        self.blockCountChanged.connect(self._update_gutter_width)
        self.updateRequest.connect(self._update_gutter)
        self.cursorPositionChanged.connect(self.refresh_extra)
        self._update_gutter_width()
        self.refresh_extra()

    # ---- appearance ----
    def set_font_size(self, pt):
        f = self.font()
        f.setPointSize(pt)
        self.setFont(f)
        self.setTabStopDistance(self.fontMetrics().horizontalAdvance(" ") * 4)
        self._update_gutter_width()

    def apply_theme(self):
        t = theme.current
        self.setStyleSheet(f"QPlainTextEdit {{ background: {t['base']}; color: {t['text']};"
                           f" selection-background-color: {t['highlight']}; selection-color: {t['hl_text']}; border: none; }}")
        self.highlighter.refresh_formats()
        self.refresh_extra()
        self.gutter.update()

    def gutter_width(self):
        digits = max(3, len(str(self.blockCount())))
        return 22 + self.fontMetrics().horizontalAdvance("9") * digits + 8

    def _update_gutter_width(self, *_):
        self.setViewportMargins(self.gutter_width(), 0, 0, 0)

    def _update_gutter(self, rect, dy):
        if dy:
            self.gutter.scroll(0, dy)
        else:
            self.gutter.update(0, rect.y(), self.gutter.width(), rect.height())

    def resizeEvent(self, ev):
        super().resizeEvent(ev)
        cr = self.contentsRect()
        self.gutter.setGeometry(QRect(cr.left(), cr.top(), self.gutter_width(), cr.height()))

    def paint_gutter(self, ev):
        t = theme.current
        p = QPainter(self.gutter)
        p.fillRect(ev.rect(), QColor(t["gutter_bg"]))
        b = self.firstVisibleBlock()
        top = self.blockBoundingGeometry(b).translated(self.contentOffset()).top()
        fm = self.fontMetrics()
        w = self.gutter.width()
        cur_line = self.textCursor().blockNumber() + 1
        while b.isValid() and top <= ev.rect().bottom():
            h = self.blockBoundingRect(b).height()
            if b.isVisible() and top + h >= ev.rect().top():
                n = b.blockNumber() + 1
                if isinstance(b.userData(), BreakpointMark):
                    p.setRenderHint(QPainter.Antialiasing)
                    p.setBrush(QColor(t["breakpoint"]))
                    p.setPen(Qt.NoPen)
                    r = min(fm.height(), 14)
                    p.drawEllipse(5, int(top + (h - r) / 2), r, r)
                if n == self.exec_line:
                    p.setPen(QColor("#e0a800"))
                    p.setBrush(QColor("#f5c518"))
                    cy = int(top + h / 2)
                    from PySide6.QtCore import QPoint
                    from PySide6.QtGui import QPolygon
                    p.drawPolygon(QPolygon([QPoint(5, cy - 6), QPoint(16, cy), QPoint(5, cy + 6)]))
                p.setPen(QColor(t["text"] if n == cur_line else t["gutter_fg"]))
                p.drawText(0, int(top), w - 8, int(h), Qt.AlignRight | Qt.AlignVCenter, str(n))
            top += h
            b = b.next()
        p.end()

    def refresh_extra(self):
        t = theme.current
        sels = []

        def line_sel(line, color):
            s = QTextEdit.ExtraSelection()
            s.format.setBackground(QColor(color))
            s.format.setProperty(QTextFormat.FullWidthSelection, True)
            block = self.document().findBlockByNumber(line - 1)
            s.cursor = QTextCursor(block)
            return s
        cur = QTextEdit.ExtraSelection()
        cur.format.setBackground(QColor(t["current_line"]))
        cur.format.setProperty(QTextFormat.FullWidthSelection, True)
        cur.cursor = self.textCursor()
        cur.cursor.clearSelection()
        sels.append(cur)
        if self.error_line:
            sels.append(line_sel(self.error_line, t["error_line"]))
        if self.exec_line:
            sels.append(line_sel(self.exec_line, t["exec_line"]))
        self.setExtraSelections(sels)
        self.gutter.update()

    # ---- breakpoints / markers ----
    @property
    def breakpoints(self):
        out = set()
        b = self.document().firstBlock()
        while b.isValid():
            if isinstance(b.userData(), BreakpointMark):
                out.add(b.blockNumber() + 1)
            b = b.next()
        return out

    def set_breakpoints(self, lines):
        b = self.document().firstBlock()
        while b.isValid():
            b.setUserData(BreakpointMark() if (b.blockNumber() + 1) in lines else None)
            b = b.next()
        self.gutter.update()
        self.breakpoints_changed.emit()

    def toggle_breakpoint(self, line=None):
        line = line or self.textCursor().blockNumber() + 1
        b = self.document().findBlockByNumber(line - 1)
        if not b.isValid():
            return
        b.setUserData(None if isinstance(b.userData(), BreakpointMark) else BreakpointMark())
        self.gutter.update()
        self.breakpoints_changed.emit()

    def set_exec_line(self, line):
        self.exec_line = line
        if line:
            self.goto_line(line, select=False)
        self.refresh_extra()

    def set_error_line(self, line):
        self.error_line = line
        if line:
            self.goto_line(line, select=False)
        self.refresh_extra()

    def goto_line(self, line, select=False):
        block = self.document().findBlockByNumber(max(0, line - 1))
        c = QTextCursor(block)
        if select:
            c.movePosition(QTextCursor.EndOfBlock, QTextCursor.KeepAnchor)
        self.setTextCursor(c)
        self.centerCursor()

    # ---- editing conveniences ----
    def keyPressEvent(self, ev):
        if ev.key() in (Qt.Key_Return, Qt.Key_Enter) and not ev.modifiers() & Qt.ShiftModifier:
            c = self.textCursor()
            line = c.block().text()
            indent = line[:len(line) - len(line.lstrip())]
            stripped = line.strip().lower()
            opens = (stripped.startswith(("for ", "while ", "do", "select case", "sub ", "function ")) or
                     (stripped.startswith("if ") and stripped.endswith("then")) or stripped == "else" or
                     stripped.startswith("case "))
            super().keyPressEvent(ev)
            self.insertPlainText(indent + ("    " if opens else ""))
            return
        if ev.key() == Qt.Key_Tab and not ev.modifiers():
            c = self.textCursor()
            if c.hasSelection():
                self.indent_selection(1)
            else:
                self.insertPlainText("    ")
            return
        if ev.key() == Qt.Key_Backtab:
            self.indent_selection(-1)
            return
        if self.error_line:
            self.error_line = None
            self.refresh_extra()
        super().keyPressEvent(ev)

    def _selected_blocks(self):
        c = self.textCursor()
        doc = self.document()
        start = doc.findBlock(c.selectionStart()).blockNumber()
        end_pos = c.selectionEnd()
        end_block = doc.findBlock(end_pos)
        end = end_block.blockNumber()
        if c.hasSelection() and end_block.position() == end_pos and end > start:
            end -= 1
        return start, end

    def indent_selection(self, direction):
        start, end = self._selected_blocks()
        c = self.textCursor()
        c.beginEditBlock()
        for n in range(start, end + 1):
            b = self.document().findBlockByNumber(n)
            bc = QTextCursor(b)
            if direction > 0:
                bc.insertText("    ")
            else:
                text = b.text()
                k = len(text) - len(text.lstrip(" "))
                k = min(k, 4) if k else (1 if text.startswith("\t") else 0)
                bc.movePosition(QTextCursor.Right, QTextCursor.KeepAnchor, k)
                bc.removeSelectedText()
        c.endEditBlock()

    def toggle_comment(self):
        start, end = self._selected_blocks()
        blocks = [self.document().findBlockByNumber(n) for n in range(start, end + 1)]
        all_commented = all(b.text().lstrip().startswith("'") or not b.text().strip() for b in blocks)
        c = self.textCursor()
        c.beginEditBlock()
        for b in blocks:
            text = b.text()
            if not text.strip():
                continue
            k = len(text) - len(text.lstrip())
            bc = QTextCursor(b)
            bc.movePosition(QTextCursor.Right, QTextCursor.MoveAnchor, k)
            if all_commented:
                bc.movePosition(QTextCursor.Right, QTextCursor.KeepAnchor, 1)
                bc.removeSelectedText()
            else:
                bc.insertText("'")
        c.endEditBlock()

    def labels(self):
        """Branch labels, SUBs and FUNCTIONs with their line numbers."""
        out = []
        b = self.document().firstBlock()
        rx_label = re.compile(r"^\s*\[([^\]\s]+)\]")
        rx_sub = re.compile(r"^\s*(sub|function)\s+([A-Za-z][\w.$]*)", re.I)
        while b.isValid():
            t = b.text()
            m = rx_label.match(t)
            if m:
                out.append((f"[{m.group(1)}]", b.blockNumber() + 1))
            else:
                m = rx_sub.match(t)
                if m:
                    out.append((f"{m.group(1).lower()} {m.group(2)}", b.blockNumber() + 1))
            b = b.next()
        return out

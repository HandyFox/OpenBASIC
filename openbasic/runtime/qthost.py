"""The Qt host: windows, events, dialogs and sound for running programs."""
import os
import subprocess
import sys
import time
from collections import deque

from PySide6.QtCore import QEventLoop, QTimer, Qt, QUrl
from PySide6.QtGui import QColor, QCursor, QGuiApplication, QImage
from PySide6.QtWidgets import (QApplication, QColorDialog, QDialog, QFileDialog, QFontDialog,
                               QInputDialog, QMenu, QMessageBox)

from ..errors import BasicError, EndProgram, StopRequested
from ..host_base import Host
from ..interp import Event
from .controls import common_cmd
from .graphics import make_sprite_frame
from .keys import KeyTracker
from .style import parse_color
from .windows import BasicWindow, ConsoleWindow


def split_title(msg, default_title):
    """Just BASIC dialogs: text before chr$(13) is the title."""
    if "\r" in msg:
        t, m = msg.split("\r", 1)
        return t, m.lstrip("\n")
    return default_title, msg


class QtHost(Host):
    def __init__(self, app, program_name="untitled.bas", debug_ui=None):
        super().__init__()
        self.app = app
        self.program_name = program_name
        self.debug_ui = debug_ui
        self.interp = None
        self.queue = deque()
        self.windows = {}
        self.controls = {}
        self.pending_controls = []
        self.pending_menus = []
        self.bitmaps = {}
        self.sprite_frames = {}
        self.console = None
        self.mainwin_enabled = True
        self.active_loops = []
        self.stop_flag = False
        self.end_flag = False
        self.last_pump = time.monotonic()
        self.inkey = ""
        self.timer = QTimer()
        self.timer.timeout.connect(self._timer_fired)
        self.timer_handler = None
        self.sound = None
        self.sound_proc = None
        self.midi = None
        self.debug_loop = None
        self.keys = KeyTracker()
        app.installEventFilter(self.keys)

    # ------------------------------------------------------------ console
    def get_console(self):
        if self.console is None:
            self.console = ConsoleWindow(self, f"{self.program_name} - OpenBASIC")
        if not self.console.isVisible():
            self.console.show()
        return self.console

    def console_write(self, text):
        self.get_console().write(text)

    def console_col(self):
        return self.console.col if self.console else 0

    def console_input(self, prompt):
        return self.get_console().read_line(prompt)

    def console_read_chars(self, n):
        return self.get_console().read_chars(n)

    def console_cls(self):
        if self.console:
            self.console.cls()

    def console_locate(self, x, y):
        self.get_console().locate(x, y)

    def nomainwin(self):
        self.mainwin_enabled = False
        if self.console and not self.console.edit.toPlainText():
            self.console.hide()

    def mainwin_size(self, cols, rows):
        from PySide6.QtGui import QFontMetrics
        con = self.console or ConsoleWindow(self, f"{self.program_name} - OpenBASIC")
        self.console = con
        fm = QFontMetrics(con.edit.font())
        con.resize(fm.horizontalAdvance("M") * max(10, cols) + 30, fm.lineSpacing() * max(3, rows) + 20)

    def set_console_title(self, title):
        con = self.console or ConsoleWindow(self, title)
        self.console = con
        con.setWindowTitle(title)

    def console_closed(self):
        self.end_flag = True
        self._quit_loops()

    def display_size(self):
        scr = QGuiApplication.primaryScreen()
        if scr is None:
            return (1024, 768)
        g = scr.geometry()
        return (g.width(), g.height())

    # ------------------------------------------------------------ windows
    def declare_control(self, spec):
        self.pending_controls.append(spec)

    def declare_menu(self, spec):
        self.pending_menus.append((spec["title"], spec["items"]))

    def open_window(self, key, title, mode, settings):
        controls, menus = self.pending_controls, self.pending_menus
        self.pending_controls, self.pending_menus = [], []
        win = BasicWindow(self, key, title, mode, settings, controls, menus)
        self.windows[key] = win
        for ckey, ctl in win.controls.items():
            self.controls[ckey] = ctl
        if "fs" in win.flags:
            win.showMaximized()
        else:
            win.show()
        win.raise_()
        win.activateWindow()
        self.app.processEvents()  # let the window reach its real size before drawing ("home")
        if win.base == "graphics":
            win.view.ensure_size(win.view.width(), win.view.height())

    def is_gui_handle(self, key):
        return key in self.windows or key in self.controls

    def gui_print(self, key, text, newline=True):
        target = self.windows.get(key) or self.controls.get(key)
        if target is None:
            win_key = key.split(".", 1)[0]
            if win_key in self.windows:
                raise BasicError(f"Window {win_key} has no control named {key}")
            raise BasicError(f"Handle {key} is not open")
        return target.command(text, self.lookup, newline)

    def _forget_window(self, key):
        win = self.windows.pop(key, None)
        if win is None:
            return None
        for ckey in list(win.controls):
            self.controls.pop(ckey, None)
        return win

    def close_gui(self, key):
        if key in self.controls and key not in self.windows:
            raise BasicError(f"{key} is a control; close its window instead")
        win = self._forget_window(key)
        if win is None:
            raise BasicError(f"Handle {key} is not open")
        win.closing_by_program = True
        win.close()
        win.deleteLater()
        self._quit_loops_if_idle()

    def window_closed_by_user(self, key):
        win = self._forget_window(key)
        if win is not None:
            win.deleteLater()
        self._quit_loops_if_idle()

    def rename_handle(self, old, new):
        win = self.windows.pop(old, None)
        if win is None:
            raise BasicError(f"Handle {old} is not open")
        win.key = new
        self.windows[new] = win
        newc = {}
        for ckey, ctl in win.controls.items():
            self.controls.pop(ckey, None)
            nk = new + ckey[len(old):]
            ctl.key = nk
            newc[nk] = ctl
            self.controls[nk] = ctl
        win.controls = newc

    def has_windows(self):
        return bool(self.windows)

    def hwnd(self, key):
        w = self.windows.get(key)
        if w is None:
            c = self.controls.get(key)
            if c is None:
                raise BasicError(f"Handle {key} is not open")
            return int(c.widget.winId())
        return int(w.winId())

    def common_widget_cmd(self, widget, op, args):
        common_cmd(widget, op, args, self)

    def lookup(self, name):
        if self.interp is None:
            return ""
        fr = self.interp.frames[-1] if self.interp.frames else None
        return self.interp.get_var_dynamic(fr, name) if fr else ""

    def resolve_path(self, p, must_exist=True):
        return self.interp.resolve(p, must_exist) if self.interp else p

    def set_inkey(self, k):
        self.inkey = k
        if self.interp:
            self.interp.gvars["Inkey$"] = k

    # ------------------------------------------------------------ events
    def push_event(self, handler, args, vars_, handle, coalesce=False):
        if not handler:
            return
        if coalesce:
            for ev in self.queue:
                if ev.handler == handler and ev.handle == handle:
                    ev.vars = vars_
                    ev.args = list(args)
                    self._quit_loops()
                    return
        self.queue.append(Event(handler, args, vars_, handle))
        if len(self.queue) > 5000:
            self.queue.popleft()
        self._quit_loops()

    def _quit_loops(self):
        for lp in self.active_loops:
            lp.quit()

    def _quit_loops_if_idle(self):
        if self._nothing_left():
            self._quit_loops()

    def _nothing_left(self):
        console_open = self.console is not None and self.console.isVisible()
        return not self.windows and not self.timer.isActive() and not console_open and not self.queue

    def wait_event(self):
        while True:
            self.check_stop()
            if self.queue:
                return self.queue.popleft()
            if self._nothing_left():
                return None
            loop = QEventLoop()
            self.active_loops.append(loop)
            try:
                loop.exec()
            finally:
                self.active_loops.remove(loop)

    def poll_event(self):
        self.check_stop()
        if self.queue:
            return self.queue.popleft()
        return None

    def set_timer(self, ms, handler):
        if not ms or ms <= 0 or handler is None:
            self.timer.stop()
            self.timer_handler = None
            self.queue = deque(e for e in self.queue if e.handle != "#timer")
            return
        self.timer_handler = handler
        self.timer.start(max(1, int(ms)))

    def _timer_fired(self):
        if self.timer_handler is None:
            return
        for ev in self.queue:
            if ev.handle == "#timer":
                return  # one pending tick at a time, like Just BASIC
        self.push_event(self.timer_handler, [], {}, "#timer")

    def pump(self, force=False):
        now = time.monotonic()
        if force or now - self.last_pump >= 0.02:
            self.last_pump = now
            self.app.processEvents()
        self.check_stop()

    def check_stop(self):
        if self.stop_flag:
            raise StopRequested()
        if self.end_flag:
            raise EndProgram()

    def request_stop(self):
        self.stop_flag = True
        self._quit_loops()
        if self.debug_loop is not None:
            self.debug_loop.quit()
        for w in QApplication.topLevelWidgets():
            if isinstance(w, QDialog) and w.isVisible() and getattr(w, "_ob_dialog", False):
                w.reject()

    # ------------------------------------------------------------ dialogs
    def _parent(self):
        w = QApplication.activeWindow()
        if w is not None:
            return w
        if self.windows:
            return list(self.windows.values())[-1]
        return self.console

    def _run_box(self, box):
        box._ob_dialog = True
        r = box.exec()
        self.check_stop()
        return r

    def notice(self, msg):
        title, text = split_title(msg, "Notice")
        box = QMessageBox(QMessageBox.Information, title, text, QMessageBox.Ok, self._parent())
        self._run_box(box)

    def confirm(self, msg):
        title, text = split_title(msg, "Please Confirm")
        box = QMessageBox(QMessageBox.Question, title, text, QMessageBox.Yes | QMessageBox.No, self._parent())
        box.setDefaultButton(QMessageBox.Yes)
        return self._run_box(box) == QMessageBox.Yes

    def prompt(self, msg, default):
        title, text = split_title(msg, "Prompt")
        dlg = QInputDialog(self._parent())
        dlg.setWindowTitle(title)
        dlg.setLabelText(text)
        dlg.setTextValue(default)
        dlg._ob_dialog = True
        ok = dlg.exec()
        self.check_stop()
        return dlg.textValue() if ok else ""

    def filedialog(self, title, template, base):
        template = template.strip() or "*.*"
        folder = base
        spec = template
        seps = [i for i, c in enumerate(template) if c in "\\/"]
        if seps:
            folder_part = template[:seps[-1]]
            spec = template[seps[-1] + 1:] or "*.*"
            folder = self.resolve_path(folder_part) if self.interp else folder_part
            if not os.path.isdir(folder):
                folder = base
        pats = [p.strip() for p in spec.replace(",", ";").split(";") if p.strip()]
        pats = ["*" if p == "*.*" else p for p in pats]
        filt = f"Files ({' '.join(pats)})"
        if "*" not in pats:
            filt += ";;All files (*)"
        dlg = QFileDialog(self._parent(), title, folder, filt)
        dlg.setFileMode(QFileDialog.AnyFile)
        dlg.setAcceptMode(QFileDialog.AcceptOpen)
        dlg._ob_dialog = True
        if dlg.exec():
            self.check_stop()
            files = dlg.selectedFiles()
            return os.path.normpath(files[0]) if files else ""
        self.check_stop()
        return ""

    def colordialog(self, color):
        try:
            initial = parse_color(color, "white")
        except BasicError:
            initial = QColor(255, 255, 255)
        c = QColorDialog.getColor(initial, self._parent(), "Color")
        self.check_stop()
        if not c.isValid():
            return ""
        return f"{c.red()} {c.green()} {c.blue()}"

    def fontdialog(self, font):
        ok, f = QFontDialog.getFont(self._parent())
        if isinstance(ok, type(f)) and not isinstance(f, bool):
            ok, f = f, ok
        self.check_stop()
        if not ok:
            return ""
        size = f.pointSize() if f.pointSize() > 0 else 10
        mods = (" bold" if f.bold() else "") + (" italic" if f.italic() else "")
        return f"{f.family().replace(' ', '_')} {size}{mods}"

    def message_box(self, title, text, buttons, icon):
        btn_sets = {
            0: QMessageBox.Ok,
            1: QMessageBox.Ok | QMessageBox.Cancel,
            2: QMessageBox.Abort | QMessageBox.Retry | QMessageBox.Ignore,
            3: QMessageBox.Yes | QMessageBox.No | QMessageBox.Cancel,
            4: QMessageBox.Yes | QMessageBox.No,
            5: QMessageBox.Retry | QMessageBox.Cancel,
        }
        icons = {"error": QMessageBox.Critical, "question": QMessageBox.Question,
                 "warning": QMessageBox.Warning, "info": QMessageBox.Information}
        box = QMessageBox(icons.get(icon, QMessageBox.NoIcon), title or " ", text,
                          btn_sets.get(buttons, QMessageBox.Ok), self._parent())
        r = self._run_box(box)
        return {QMessageBox.Ok: 1, QMessageBox.Cancel: 2, QMessageBox.Abort: 3, QMessageBox.Retry: 4,
                QMessageBox.Ignore: 5, QMessageBox.Yes: 6, QMessageBox.No: 7}.get(r, 1)

    def popupmenu(self, items):
        m = QMenu()
        actions = {}
        for it in items:
            if it is None:
                m.addSeparator()
                continue
            a = m.addAction(it[0].replace("&&", "&"))
            actions[a] = it[1]
        chosen = m.exec(QCursor.pos())
        self.check_stop()
        return actions.get(chosen) if chosen else None

    # ------------------------------------------------------------ bitmaps
    def load_image_file(self, path):
        img = QImage(path)
        if img.isNull():
            try:
                from PIL import Image
                im = Image.open(path).convert("RGBA")
                data = im.tobytes("raw", "BGRA")
                img = QImage(data, im.width, im.height, QImage.Format_ARGB32).copy()
            except Exception:
                raise BasicError(f"Can't read image file {path}")
        return img

    def load_bmp(self, name, path):
        self.bitmaps[name.lower()] = self.load_image_file(path)
        self.sprite_frames.pop(name.lower(), None)

    def unload_bmp(self, name):
        self.bitmaps.pop(name.lower(), None)
        self.sprite_frames.pop(name.lower(), None)

    def save_bmp(self, name, path):
        if not self.get_bitmap(name).save(path, "BMP"):
            raise BasicError(f"Couldn't save bitmap to {path}")

    def get_bitmap(self, name):
        img = self.bitmaps.get(name.lower())
        if img is None:
            raise BasicError(f"Bitmap '{name}' isn't loaded (use LOADBMP first)")
        return img

    def get_sprite_frame(self, name):
        f = self.sprite_frames.get(name.lower())
        if f is None:
            f = make_sprite_frame(self.get_bitmap(name))
            self.sprite_frames[name.lower()] = f
        return f

    # ------------------------------------------------------------ sound
    def playwave(self, path, mode):
        self._stop_sound()
        if path is None:
            return
        mode = (mode or "sync").lower()
        try:
            from PySide6.QtMultimedia import QSoundEffect
            eff = QSoundEffect()
            eff.setSource(QUrl.fromLocalFile(os.path.abspath(path)))
            eff.setLoopCount(QSoundEffect.Infinite if mode == "loop" else 1)
            eff.setVolume(1.0)
            eff.play()
            self.sound = eff
            if mode == "sync":
                start = time.monotonic()
                while time.monotonic() - start < 0.5 and eff.status() == QSoundEffect.Loading:
                    self.pump(force=True)
                    time.sleep(0.005)
                while eff.isPlaying() or eff.status() == QSoundEffect.Loading:
                    self.pump(force=True)
                    time.sleep(0.01)
                    if time.monotonic() - start > 600:
                        break
            return
        except ImportError:
            pass
        self._play_external(path, mode)

    def _play_external(self, path, mode):
        if sys.platform.startswith("win"):
            import winsound
            flags = winsound.SND_FILENAME
            if mode != "sync":
                flags |= winsound.SND_ASYNC
            if mode == "loop":
                flags |= winsound.SND_LOOP
            winsound.PlaySound(path, flags)
            return
        player = ["afplay", path] if sys.platform == "darwin" else ["aplay", "-q", path]
        try:
            self.sound_proc = subprocess.Popen(player)
            if mode == "sync":
                while self.sound_proc.poll() is None:
                    self.pump(force=True)
                    time.sleep(0.01)
        except OSError:
            pass

    def _stop_sound(self):
        if self.sound is not None:
            try:
                self.sound.stop()
            except RuntimeError:
                pass
            self.sound = None
        if self.sound_proc is not None:
            try:
                self.sound_proc.terminate()
            except OSError:
                pass
            self.sound_proc = None
        if sys.platform.startswith("win"):
            try:
                import winsound
                winsound.PlaySound(None, 0)
            except Exception:
                pass

    def playmidi(self, path, times):
        self.stopmidi()
        try:
            from PySide6.QtMultimedia import QMediaPlayer, QAudioOutput
            p = QMediaPlayer()
            out = QAudioOutput()
            p.setAudioOutput(out)
            p.setSource(QUrl.fromLocalFile(os.path.abspath(path)))
            p.setLoops(max(1, int(times)))
            p.play()
            self.midi = (p, out)
            return int(p.duration() // 1000)
        except Exception:
            return 0

    def midipos(self):
        if self.midi:
            return int(self.midi[0].position() // 1000)
        return 0

    def stopmidi(self):
        if self.midi:
            try:
                self.midi[0].stop()
            except RuntimeError:
                pass
            self.midi = None

    def beep(self):
        QApplication.beep()

    def key_state(self, vk):
        return self.keys.state(vk)

    # ------------------------------------------------------------ debugger
    def debug_pause(self, interp, fr, line):
        if self.debug_ui is None:
            return
        self.debug_ui.on_debug_pause(interp, fr, line)
        self.debug_loop = QEventLoop()
        self.active_loops.append(self.debug_loop)
        try:
            self.debug_loop.exec()
        finally:
            self.active_loops.remove(self.debug_loop)
            self.debug_loop = None
        self.check_stop()
        self.debug_ui.on_debug_resume()

    def debug_resume(self):
        if self.debug_loop is not None:
            self.debug_loop.quit()

    def debug_animate(self, interp, fr, line):
        if self.debug_ui is None:
            return
        self.debug_ui.on_debug_line(interp, fr, line)
        end = time.monotonic() + self.debug_ui.animate_delay()
        while time.monotonic() < end:
            self.app.processEvents()
            self.check_stop()
            time.sleep(0.005)

    # ------------------------------------------------------------ cleanup
    def shutdown(self):
        self.timer.stop()
        self._stop_sound()
        self.stopmidi()
        for key in list(self.windows):
            win = self._forget_window(key)
            win.closing_by_program = True
            win.close()
            win.deleteLater()
        self.pending_controls.clear()
        self.pending_menus.clear()
        self.queue.clear()
        if self.console is not None:
            self.console.program_running = False
        try:
            self.app.removeEventFilter(self.keys)
        except RuntimeError:
            pass

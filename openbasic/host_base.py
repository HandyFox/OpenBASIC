"""The host interface the interpreter talks to, plus a headless host for
tests and command-line use (console programs only)."""
import sys

from .errors import BasicError


class Host:
    """Base host: console only, no windows. Subclasses override what they support."""

    def __init__(self):
        self.col = 0
        self.timer = None

    # console
    def console_write(self, text):
        sys.stdout.write(text)
        sys.stdout.flush()
        self._track(text)

    def _track(self, text):
        nl = text.rfind("\n")
        self.col = len(text) - nl - 1 if nl >= 0 else self.col + len(text)

    def console_col(self):
        return self.col

    def console_input(self, prompt):
        self.console_write(prompt)
        line = sys.stdin.readline()
        self.col = 0
        return line.rstrip("\r\n")

    def console_read_chars(self, n):
        return sys.stdin.read(n)

    def console_cls(self):
        pass

    def console_locate(self, x, y):
        pass

    def nomainwin(self):
        pass

    def display_size(self):
        return (1024, 768)

    # windows
    def declare_control(self, spec):
        raise BasicError("Windows and controls need the graphical runtime")

    def declare_menu(self, spec):
        raise BasicError("Menus need the graphical runtime")

    def open_window(self, key, title, mode, settings):
        raise BasicError("Windows need the graphical runtime")

    def is_gui_handle(self, key):
        return False

    def gui_print(self, key, text, newline=True):
        raise BasicError(f"Handle {key} is not open")

    def close_gui(self, key):
        pass

    def rename_handle(self, old, new):
        raise BasicError(f"Handle {old} is not open")

    def has_windows(self):
        return False

    def hwnd(self, key):
        return 0

    # events
    def wait_event(self):
        return None

    def poll_event(self):
        return None

    def set_timer(self, ms, handler):
        self.timer = (ms, handler) if ms else None

    def pump(self, force=False):
        pass

    # dialogs
    def notice(self, msg):
        self.console_write(msg.replace("\r", "\n") + "\n")

    def confirm(self, msg):
        return False

    def prompt(self, msg, default):
        return default

    def filedialog(self, title, template, base):
        return ""

    def colordialog(self, color):
        return ""

    def fontdialog(self, font):
        return ""

    def message_box(self, title, text, buttons, icon):
        self.notice(title + "\r" + text)
        return 1

    def popupmenu(self, items):
        return None

    # system
    def run_command(self, cmd, mode, cwd):
        from .platform_run import run_command
        run_command(cmd, mode, cwd)

    def load_bmp(self, name, path):
        pass

    def unload_bmp(self, name):
        pass

    def playwave(self, path, mode):
        pass

    def playmidi(self, path, times):
        return 0

    def midipos(self):
        return 0

    def stopmidi(self):
        pass

    def beep(self):
        pass

    def key_state(self, vk):
        return 0

    # debugger
    def debug_pause(self, interp, fr, line):
        pass

    def debug_animate(self, interp, fr, line):
        pass


class TestHost(Host):
    __test__ = False  # not a pytest test class
    """Captures console output; feeds INPUT from a list. GUI calls are recorded."""

    def __init__(self, inputs=()):
        super().__init__()
        self.out = []
        self.inputs = list(inputs)
        self.events = []
        self.gui = []
        self.notices = []
        self.confirm_answers = []
        self.windows = set()

    def console_write(self, text):
        self.out.append(text)
        self._track(text)

    def console_input(self, prompt):
        self.console_write(prompt)
        self.col = 0
        v = self.inputs.pop(0) if self.inputs else ""
        self.out.append(v + "\n")
        return v

    def output(self):
        return "".join(self.out)

    def notice(self, msg):
        self.notices.append(msg)

    def confirm(self, msg):
        self.notices.append(msg)
        return self.confirm_answers.pop(0) if self.confirm_answers else False

    def wait_event(self):
        return self.events.pop(0) if self.events else None

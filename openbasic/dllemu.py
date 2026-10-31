"""CALLDLL support.

Windows API calls can't work on macOS or Linux, so the most common ones are
emulated on every platform. On Windows, calls that aren't emulated are passed
through to the real DLL with ctypes.
"""
import os
import sys
import time

from .errors import BasicError
from .values import to_str

MB_ICONS = {0x10: "error", 0x20: "question", 0x30: "warning", 0x40: "info"}


def _a(args, i, default=0):
    return args[i][0] if i < len(args) else default


def _msgbox(interp, args):
    text = to_str(_a(args, 1, ""))
    title = to_str(_a(args, 2, ""))
    flags = int(_a(args, 3, 0) or 0)
    return interp.host.message_box(title, text, flags & 0x0F, MB_ICONS.get(flags & 0xF0))


def _sleep(interp, args):
    ms = int(_a(args, 0, 0))
    end = time.monotonic() + ms / 1000.0
    while time.monotonic() < end:
        interp.host.pump(force=True)
        time.sleep(min(0.01, max(0, end - time.monotonic())))
    return 0


def _tick(interp, args):
    return int(time.monotonic() * 1000) & 0xFFFFFFFF


def _beep(interp, args):
    interp.host.beep()
    return 1


def _play_sound(interp, args):
    name = to_str(_a(args, 0, ""))
    if not name:
        interp.host.playwave(None, "async")
        return 1
    real = interp.resolve(name)
    if os.path.exists(real):
        interp.host.playwave(real, "async")
        return 1
    return 0


def _metrics(interp, args):
    idx = int(_a(args, 0, 0))
    w, h = interp.host.display_size()
    return {0: w, 1: h}.get(idx, 0)


def _keystate(interp, args):
    return interp.host.key_state(int(_a(args, 0, 0)))


def _set_title(interp, args):
    return 1


def _shell_exec(interp, args):
    # ShellExecuteA(hwnd, verb, file, params, dir, show)
    target = to_str(_a(args, 2, ""))
    params = to_str(_a(args, 3, ""))
    cmd = target + (" " + params if params else "")
    interp.host.run_command(cmd, None, interp.gvars["DefaultDir$"])
    return 33


EMULATED = {
    "messageboxa": _msgbox,
    "messageboxw": _msgbox,
    "messagebox": _msgbox,
    "sleep": _sleep,
    "gettickcount": _tick,
    "timegettime": _tick,
    "messagebeep": _beep,
    "beep": _beep,
    "sndplaysounda": _play_sound,
    "playsounda": _play_sound,
    "getsystemmetrics": _metrics,
    "getasynckeystate": _keystate,
    "getkeystate": _keystate,
    "setwindowtexta": _set_title,
    "shellexecutea": _shell_exec,
}


def call_dll(interp, lib, func, args, ret_type):
    key = func.lower()
    f = EMULATED.get(key)
    if f is not None:
        return f(interp, args)
    if sys.platform.startswith("win"):
        return _real_call(lib, func, args, ret_type)
    raise BasicError(f"CALLDLL {lib}:{func} is a Windows-only API call and isn't emulated on this "
                     f"computer. Emulated calls: MessageBoxA, Sleep, GetTickCount, Beep, "
                     f"sndPlaySoundA, GetSystemMetrics, GetAsyncKeyState, ShellExecuteA.")


def _real_call(lib, func, args, ret_type):  # pragma: no cover - Windows only
    import ctypes
    name = lib.lstrip("#")
    aliases = {"user": "user32", "kernel": "kernel32", "gdi": "gdi32"}
    name = aliases.get(name.lower(), name)
    try:
        dll = ctypes.WinDLL(name)
        fn = getattr(dll, func)
    except (OSError, AttributeError):
        raise BasicError(f"CALLDLL: can't find {func} in {name}")
    conv = []
    for v, t in args:
        if isinstance(v, str):
            conv.append(ctypes.c_char_p(v.encode("latin-1", "replace")))
        elif t in ("double",):
            conv.append(ctypes.c_double(v))
        else:
            conv.append(ctypes.c_long(int(v)))
    if ret_type == "double":
        fn.restype = ctypes.c_double
    elif ret_type == "void":
        fn.restype = None
    else:
        fn.restype = ctypes.c_long
    return fn(*conv) or 0

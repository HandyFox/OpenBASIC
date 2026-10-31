"""RUN statement support across platforms.

On Windows commands run as written. On macOS and Linux common Windows
programs are translated:

    cmd.exe [/k|/c command]   -> a terminal window running the command
    notepad.exe file          -> the default text editor
    explorer.exe path-or-url  -> the default file browser / web browser
    calc.exe                  -> the system calculator
    mspaint.exe file          -> the default image viewer
    a document or URL         -> opened with its default application
"""
import os
import shlex
import shutil
import subprocess
import sys

from .errors import BasicError

IS_WIN = sys.platform.startswith("win")
IS_MAC = sys.platform == "darwin"


def _split(cmd):
    cmd = cmd.strip()
    if cmd.startswith('"'):
        j = cmd.find('"', 1)
        if j > 0:
            return cmd[1:j], cmd[j + 1:].strip()
    parts = cmd.split(None, 1)
    return (parts[0], parts[1] if len(parts) > 1 else "")


def _open_default(target, cwd):
    if IS_MAC:
        subprocess.Popen(["open", target], cwd=cwd)
    elif IS_WIN:
        os.startfile(target)  # type: ignore[attr-defined]
    else:
        subprocess.Popen(["xdg-open", target], cwd=cwd,
                         stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)


def _terminal(command, keep_open, cwd):
    if IS_MAC:
        script = f"cd {shlex.quote(cwd)}" + (f"; {command}" if command else "")
        if not keep_open and command:
            script += "; exit"
        esc = script.replace("\\", "\\\\").replace('"', '\\"')
        subprocess.Popen(["osascript", "-e", f'tell application "Terminal" to do script "{esc}"',
                          "-e", 'tell application "Terminal" to activate'])
        return
    shell_cmd = command or ""
    if keep_open or not command:
        shell_cmd = (command + "; " if command else "") + "exec ${SHELL:-bash}"
    candidates = [
        ("x-terminal-emulator", ["-e", "bash", "-c", shell_cmd]),
        ("gnome-terminal", ["--", "bash", "-c", shell_cmd]),
        ("konsole", ["-e", "bash", "-c", shell_cmd]),
        ("xfce4-terminal", ["-x", "bash", "-c", shell_cmd]),
        ("xterm", ["-e", "bash", "-c", shell_cmd]),
    ]
    for exe, args in candidates:
        if shutil.which(exe):
            subprocess.Popen([exe] + args, cwd=cwd)
            return
    # no terminal found: just run the command in the background
    if command:
        subprocess.Popen(command, shell=True, cwd=cwd)
    else:
        raise BasicError("RUN cmd.exe: no terminal program was found on this computer")


def run_command(cmd, mode, cwd):
    cwd = cwd if cwd and os.path.isdir(cwd) else os.getcwd()
    if not cmd.strip():
        return
    if IS_WIN:
        flags = 0
        startupinfo = None
        if mode in ("hide",):
            startupinfo = subprocess.STARTUPINFO()
            startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW
            startupinfo.wShowWindow = 0
        elif mode in ("showminimized", "minimize"):
            startupinfo = subprocess.STARTUPINFO()
            startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW
            startupinfo.wShowWindow = 7
        exe, _ = _split(cmd)
        if exe.lower().endswith(("cmd.exe", "cmd")):
            flags = subprocess.CREATE_NEW_CONSOLE
        try:
            subprocess.Popen(cmd, cwd=cwd, creationflags=flags, startupinfo=startupinfo)
        except OSError:
            try:
                os.startfile(cmd)  # documents and URLs
            except OSError as e:
                raise BasicError(f"RUN failed: {e}")
        return

    exe, rest = _split(cmd)
    base = os.path.basename(exe.replace("\\", "/")).lower()
    if base.endswith(".exe"):
        base = base[:-4]
    try:
        if base == "cmd":
            low = rest.lower()
            keep = True
            command = ""
            if low.startswith("/k"):
                command = rest[2:].strip()
            elif low.startswith("/c"):
                command = rest[2:].strip()
                keep = False
            elif rest:
                command = rest
            _terminal(command, keep, cwd)
            return
        if base in ("notepad", "write", "wordpad"):
            target = rest.strip().strip('"')
            if target:
                from .paths import resolve
                real = resolve(target, cwd, must_exist=True)
                if not os.path.exists(real):
                    open(real, "a").close()
                if IS_MAC:
                    subprocess.Popen(["open", "-t", real])
                else:
                    _open_default(real, cwd)
            else:
                if IS_MAC:
                    subprocess.Popen(["open", "-a", "TextEdit"])
                else:
                    for ed in ("gedit", "gnome-text-editor", "kate", "mousepad", "xed", "leafpad"):
                        if shutil.which(ed):
                            subprocess.Popen([ed])
                            break
            return
        if base in ("explorer", "start"):
            target = rest.strip().strip('"') or cwd
            if "://" not in target:
                from .paths import resolve
                target = resolve(target, cwd, must_exist=True)
            _open_default(target, cwd)
            return
        if base == "calc":
            if IS_MAC:
                subprocess.Popen(["open", "-a", "Calculator"])
            else:
                for c in ("gnome-calculator", "kcalc", "galculator", "xcalc"):
                    if shutil.which(c):
                        subprocess.Popen([c])
                        break
            return
        if base == "mspaint":
            target = rest.strip().strip('"')
            if target:
                from .paths import resolve
                _open_default(resolve(target, cwd, must_exist=True), cwd)
            return
        if "://" in cmd or (not rest and os.path.exists(os.path.join(cwd, exe))
                            and not os.access(os.path.join(cwd, exe), os.X_OK)):
            _open_default(cmd.strip(), cwd)
            return
        subprocess.Popen(cmd, shell=True, cwd=cwd)
    except OSError as e:
        raise BasicError(f"RUN failed: {e}")

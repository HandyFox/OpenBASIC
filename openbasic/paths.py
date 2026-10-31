"""Cross-platform path handling for programs written on Windows.

Just BASIC programs use backslashes, drive letters and assume a
case-insensitive file system. These helpers make such paths work on
macOS and Linux too:

* backslashes become the native separator,
* relative paths are resolved against the program's folder (DefaultDir$),
* file names are matched case-insensitively ("PHONELOG.TXT" finds "PHONELOG.txt"),
* an absolute Windows path that doesn't exist (C:\\My Basic Files\\Barn.bmp)
  falls back to the same file name inside the program's folder.
"""
import os
import re
import sys

IS_WINDOWS = sys.platform.startswith("win")
_DRIVE = re.compile(r"^[A-Za-z]:[\\/]")


def _split(p):
    return [x for x in re.split(r"[\\/]+", p) if x not in ("",)]


def _ci_join(base, parts):
    """Join parts onto base, matching each part case-insensitively if needed."""
    cur = base
    for i, part in enumerate(parts):
        cand = os.path.join(cur, part)
        if os.path.exists(cand):
            cur = cand
            continue
        try:
            entries = os.listdir(cur)
        except OSError:
            return None
        low = part.lower()
        match = next((e for e in entries if e.lower() == low), None)
        if match is None:
            return None
        cur = os.path.join(cur, match)
    return cur


def resolve(path, base_dir, must_exist=False):
    """Return a usable native path for a BASIC file name.

    When must_exist is True, try hard to find an existing file and return
    the best guess even if nothing is found. When it is False (writing a
    file) prefer an existing case-insensitive match, else the plain path.
    """
    if path is None:
        return path
    p = path.strip()
    if not p:
        return p
    if IS_WINDOWS:
        full = p if os.path.isabs(p) else os.path.join(base_dir, p)
        return os.path.normpath(full)

    is_drive = bool(_DRIVE.match(p))
    is_abs = is_drive or p.startswith("/") or (p.startswith("\\") and not p.startswith("\\\\"))
    parts = _split(p[2:] if is_drive else p)

    if not is_drive and p.startswith("/"):
        root = "/"
    elif is_abs:
        root = None  # a Windows absolute path: no direct equivalent
    else:
        root = base_dir

    if root is not None:
        found = _ci_join(root, parts)
        if found:
            return found

    if is_abs or is_drive:
        # try the tail of the path inside the program folder, longest first
        for k in range(len(parts)):
            found = _ci_join(base_dir, parts[k:])
            if found:
                return found
        if root is None:
            # nothing found: write next to the program, keeping the file name
            return os.path.join(base_dir, *parts[-1:]) if parts else base_dir
        return os.path.join(root, *parts)

    if not must_exist and parts:
        # writing: match an existing folder case-insensitively, keep new name
        parent = _ci_join(base_dir, parts[:-1]) if len(parts) > 1 else base_dir
        if parent:
            existing = _ci_join(parent, parts[-1:])
            return existing or os.path.join(parent, parts[-1])
    return os.path.join(base_dir, *parts)


def to_basic(path):
    """Present a native path the way the program expects it."""
    return path

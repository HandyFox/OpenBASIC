"""Standalone apps: a copy of the OpenBASIC runtime plus a packed program file.

Like Just BASIC's runtime + .TKN files, a standalone app is the runtime
executable renamed to the program's name, with a matching .obp file beside it
(inside Contents/Resources for a macOS .app). The .obp holds the program's
source, compressed so it isn't casually edited.
"""
import json
import os
import sys
import zlib

MAGIC = b"OBP1\n"


def pack(source, name):
    header = json.dumps({"name": name}).encode("utf-8")
    return MAGIC + header + b"\n" + zlib.compress(source.encode("utf-8"), 9)


def unpack(data):
    if not data.startswith(MAGIC):
        raise ValueError("not an OpenBASIC program file")
    rest = data[len(MAGIC):]
    nl = rest.index(b"\n")
    header = json.loads(rest[:nl].decode("utf-8"))
    return header.get("name", "program.bas"), zlib.decompress(rest[nl + 1:]).decode("utf-8")


def _candidate_dirs(exe):
    d = os.path.dirname(os.path.abspath(exe))
    dirs = [d]
    # macOS: .../Name.app/Contents/MacOS/exe
    if os.path.basename(d) == "MacOS" and os.path.basename(os.path.dirname(d)) == "Contents":
        contents = os.path.dirname(d)
        dirs.insert(0, os.path.join(contents, "Resources"))
        dirs.append(os.path.dirname(os.path.dirname(contents)))
    return dirs


def find_bundled_program():
    """Return (path, source) when running as a standalone app, else None."""
    if not getattr(sys, "frozen", False) and not os.environ.get("OPENBASIC_STANDALONE"):
        return None
    exe = sys.executable if getattr(sys, "frozen", False) else os.environ["OPENBASIC_STANDALONE"]
    stem = os.path.splitext(os.path.basename(exe))[0]
    for d in _candidate_dirs(exe):
        if not os.path.isdir(d):
            continue
        for name in (stem + ".obp", stem + ".bas"):
            p = os.path.join(d, name)
            if os.path.exists(p):
                return _load(p)
        # inside a macOS .app the executable keeps the runtime's name, so accept
        # the single packed program in Contents/Resources
        if os.path.basename(d) == "Resources":
            obps = [f for f in os.listdir(d) if f.lower().endswith(".obp")]
            if len(obps) == 1:
                return _load(os.path.join(d, obps[0]))
    return None


def _load(p):
    with open(p, "rb") as f:
        data = f.read()
    if p.lower().endswith(".obp"):
        name, source = unpack(data)
        # Files the program opens are found relative to the .obp's folder.
        return os.path.join(os.path.dirname(p), name), source
    return p, data.decode("utf-8", errors="replace")

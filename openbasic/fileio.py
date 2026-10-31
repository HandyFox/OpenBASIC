"""File handles for OPEN ... FOR INPUT/OUTPUT/APPEND/RANDOM/BINARY."""
import os

from .errors import BasicError
from .values import val

NEWLINE = "\r\n" if os.name == "nt" else "\n"


def _decode(data):
    try:
        return data.decode("utf-8")
    except UnicodeDecodeError:
        return data.decode("latin-1")


def _encode(text):
    try:
        return text.encode("latin-1")
    except UnicodeEncodeError:
        return text.encode("utf-8")


class BFile:
    def __init__(self, handle, path, mode, reclen=None):
        self.handle = handle
        self.path = path
        self.mode = mode
        self.col = 0
        self.reclen = int(reclen) if reclen else 128
        self.fields = []
        self.pos = 0
        try:
            if mode == "input":
                with open(path, "rb") as f:
                    self.text = _decode(f.read())
                self.f = None
            elif mode == "output":
                self.f = open(path, "wb")
            elif mode == "append":
                self.f = open(path, "ab")
            elif mode in ("random", "binary"):
                if not os.path.exists(path):
                    open(path, "wb").close()
                self.f = open(path, "r+b")
            else:
                raise BasicError(f"Unknown file mode '{mode}'")
        except FileNotFoundError:
            raise BasicError(f"File not found: {path}")
        except IsADirectoryError:
            raise BasicError(f"'{path}' is a folder, not a file")
        except PermissionError:
            raise BasicError(f"Permission denied opening {path}")

    # ---- writing ----
    def write(self, text):
        if self.mode == "input":
            raise BasicError(f"{self.handle} was opened for INPUT; it can't be written to")
        if self.mode in ("output", "append", "binary"):
            self.f.write(_encode(text.replace("\n", NEWLINE) if self.mode != "binary" else text))
        else:
            raise BasicError(f"Use FIELD and PUT to write to random file {self.handle}")
        nl = text.rfind("\n")
        self.col = len(text) - nl - 1 if nl >= 0 else self.col + len(text)

    # ---- reading ----
    def _need_input(self):
        if self.mode == "binary":
            return
        if self.mode != "input":
            raise BasicError(f"{self.handle} was not opened for INPUT")

    def eof(self):
        if self.mode == "input":
            return -1 if self.pos >= len(self.text) else 0
        if self.mode in ("binary", "random"):
            cur = self.f.tell()
            self.f.seek(0, 2)
            end = self.f.tell()
            self.f.seek(cur)
            return -1 if cur >= end else 0
        return -1

    def lof(self):
        if self.mode == "input":
            return len(self.text.encode("latin-1", "replace"))
        self.f.flush()
        return os.path.getsize(self.path)

    def loc(self):
        if self.mode == "input":
            return self.pos
        return self.f.tell()

    def _binary_text(self):
        data = self.f.read()
        return data.decode("latin-1")

    def read_line(self):
        self._need_input()
        if self.mode == "binary":
            start = self.f.tell()
            rest = self._binary_text()
            j = rest.find("\n")
            line = rest if j < 0 else rest[:j]
            self.f.seek(start + (len(rest) if j < 0 else j + 1))
            return line.rstrip("\r")
        t = self.text
        if self.pos >= len(t):
            return ""
        j = t.find("\n", self.pos)
        if j < 0:
            line = t[self.pos:]
            self.pos = len(t)
        else:
            line = t[self.pos:j]
            self.pos = j + 1
        return line.rstrip("\r")

    def read_item(self):
        """INPUT #h, var: read up to a comma or end of line."""
        self._need_input()
        if self.mode == "binary":
            return self.read_line()
        t = self.text
        n = len(t)
        i = self.pos
        while i < n and t[i] in " \t":
            i += 1
        if i < n and t[i] == '"':
            j = t.find('"', i + 1)
            if j < 0:
                j = n
            item = t[i + 1:j]
            i = j + 1
            while i < n and t[i] not in ",\n":
                i += 1
        else:
            j = i
            while j < n and t[j] not in ",\n":
                j += 1
            item = t[i:j].rstrip("\r").rstrip()
            i = j
        if i < n and t[i] in ",\n":
            i += 1
        self.pos = i
        return item

    def read_chars(self, count):
        if self.mode == "input":
            s = self.text[self.pos:self.pos + count]
            self.pos += len(s)
            return s
        return self.f.read(count).decode("latin-1")

    def seek(self, pos):
        if self.mode == "input":
            self.pos = int(pos)
        else:
            self.f.seek(int(pos))

    # ---- random access ----
    def put(self, rec, values):
        if self.mode != "random":
            raise BasicError(f"PUT needs a file opened FOR RANDOM ({self.handle})")
        buf = ""
        for (width, value) in values:
            s = value if isinstance(value, str) else str(value)
            buf += s[:width].ljust(width)
        buf = buf[:self.reclen].ljust(self.reclen)
        self.f.seek((int(rec) - 1) * self.reclen)
        self.f.write(buf.encode("latin-1", "replace"))

    def get(self, rec, widths):
        if self.mode != "random":
            raise BasicError(f"GET needs a file opened FOR RANDOM ({self.handle})")
        self.f.seek((int(rec) - 1) * self.reclen)
        data = self.f.read(self.reclen).decode("latin-1").ljust(self.reclen)
        out = []
        p = 0
        for w in widths:
            out.append(data[p:p + w])
            p += w
        return out

    def close(self):
        if self.f:
            try:
                self.f.close()
            finally:
                self.f = None


def read_value(item, is_str):
    return item if is_str else val(item)

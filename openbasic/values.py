"""Value helpers: number formatting, conversions, arrays."""
import math

from .errors import BasicError


class TabMarker:
    """Returned by TAB(n) inside PRINT."""
    __slots__ = ("col",)

    def __init__(self, col):
        self.col = col


def fmt_num(v):
    if isinstance(v, bool):
        v = int(v)
    if isinstance(v, int):
        return str(v)
    if v != v:
        return "NaN"
    if v in (math.inf, -math.inf):
        return "Infinity" if v > 0 else "-Infinity"
    if v.is_integer() and abs(v) < 1e15:
        return str(int(v))
    a = abs(v)
    if a >= 1e15 or a < 1e-5:
        s = f"{v:.9g}"
        if "e" in s:
            mant, exp = s.split("e")
            if "." in mant:
                mant = mant.rstrip("0").rstrip(".")
            sign = exp[0]
            digits = exp[1:].lstrip("0") or "0"
            return f"{mant}e{'-' if sign == '-' else ''}{digits}"
        return s
    s = f"{v:.8f}".rstrip("0").rstrip(".")
    if s in ("-0", ""):
        s = "0"
    return s


def to_str(v):
    if isinstance(v, str):
        return v
    if isinstance(v, TabMarker):
        return ""
    return fmt_num(v)


def val(s):
    """VAL(): read the leading number from a string, 0 if none."""
    s = s.strip()
    if not s:
        return 0
    i = 0
    n = len(s)
    if i < n and s[i] in "+-":
        i += 1
    start_digits = i
    while i < n and s[i].isdigit():
        i += 1
    if i < n and s[i] == ".":
        i += 1
        while i < n and s[i].isdigit():
            i += 1
    if i == start_digits or s[start_digits:i] == ".":
        return 0
    if i < n and s[i] in "eE":
        j = i + 1
        if j < n and s[j] in "+-":
            j += 1
        if j < n and s[j].isdigit():
            while j < n and s[j].isdigit():
                j += 1
            i = j
    text = s[:i]
    try:
        if any(c in text for c in ".eE"):
            f = float(text)
            return f
        return int(text)
    except ValueError:
        return 0


def normalize_num(v):
    """Turn integral floats into ints so printing and indexing stay tidy."""
    if isinstance(v, float) and v.is_integer() and abs(v) < 1e15:
        return int(v)
    return v


class BArray:
    __slots__ = ("name", "dims", "data", "default")

    def __init__(self, name, dims):
        self.name = name
        self.default = "" if name.endswith("$") else 0
        self.redim(dims)

    def redim(self, dims):
        dims = [int(d) for d in dims]
        if not dims or len(dims) > 2:
            raise BasicError(f"Array {self.name}() must have one or two dimensions")
        for d in dims:
            if d < 0:
                raise BasicError(f"Array {self.name}() can't have a negative size")
        self.dims = [d + 1 for d in dims]
        size = 1
        for d in self.dims:
            size *= d
        if size > 50_000_000:
            raise BasicError(f"Array {self.name}() is too large")
        self.data = [self.default] * size

    def _offset(self, idx):
        if len(idx) != len(self.dims):
            raise BasicError(
                f"Array {self.name}() has {len(self.dims)} dimension(s) but was used with {len(idx)}")
        off = 0
        for i, d in zip(idx, self.dims):
            i = int(i)
            if i < 0 or i >= d:
                raise BasicError(
                    f"Subscript out of range: {self.name}({', '.join(str(int(x)) for x in idx)}); "
                    f"largest index is {d - 1}. Use DIM to make it bigger.")
            off = off * d + i
        return off

    def get(self, idx):
        return self.data[self._offset(idx)]

    def set(self, idx, v):
        self.data[self._offset(idx)] = v

    def items_1d(self):
        if len(self.dims) == 1:
            return list(self.data)
        # first column of a 2-D array
        return [self.data[i * self.dims[1]] for i in range(self.dims[0])]

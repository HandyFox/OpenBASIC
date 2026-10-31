"""Built-in functions. Each entry is name -> (function(interp, frame, *args), takes_handles)."""
import datetime
import math
import os
import random
import time

from .errors import BasicError
from .values import TabMarker, fmt_num, normalize_num, to_str, val

BUILTINS = {}


def builtin(name, handles=False):
    def deco(f):
        BUILTINS[name] = (f, handles)
        return f
    return deco


def _n(v, fname):
    if isinstance(v, str):
        raise BasicError(f"{fname}() needs a number, not a string")
    return v


def _s(v, fname):
    if not isinstance(v, str):
        raise BasicError(f"{fname}() needs a string, not a number")
    return v


def _args(fname, args, lo, hi):
    if not (lo <= len(args) <= hi):
        if lo == hi:
            raise BasicError(f"{fname}() takes {lo} argument(s)")
        raise BasicError(f"{fname}() takes {lo} to {hi} arguments")


# ---- math ----
def _math1(name, f, domain=None):
    def fn(interp, fr, *a):
        _args(name, a, 1, 1)
        x = _n(a[0], name)
        try:
            return normalize_num(f(x))
        except ValueError:
            raise BasicError(f"{name}({fmt_num(x)}) is out of range")
        except OverflowError:
            raise BasicError(f"{name}(): number too large")
    BUILTINS[name] = (fn, False)


_math1("abs", abs)
_math1("sin", math.sin)
_math1("cos", math.cos)
_math1("tan", math.tan)
_math1("atn", math.atan)
_math1("asn", math.asin)
_math1("acs", math.acos)
_math1("exp", math.exp)
_math1("sqr", math.sqrt)
_math1("sgn", lambda x: (x > 0) - (x < 0))


@builtin("log")
def _log(interp, fr, *a):
    _args("log", a, 1, 1)
    x = _n(a[0], "log")
    if x <= 0:
        raise BasicError("log() needs a number greater than zero")
    return math.log(x)


@builtin("int")
def _int(interp, fr, *a):
    _args("int", a, 1, 1)
    x = _n(a[0], "int")
    if isinstance(x, int):
        return x
    return int(math.floor(x)) if x >= 0 else -int(math.floor(-x))


@builtin("rnd")
def _rnd(interp, fr, *a):
    return random.random()


@builtin("min")
def _min(interp, fr, *a):
    _args("min", a, 2, 2)
    return min(_n(a[0], "min"), _n(a[1], "min"))


@builtin("max")
def _max(interp, fr, *a):
    _args("max", a, 2, 2)
    return max(_n(a[0], "max"), _n(a[1], "max"))


@builtin("not")
def _notf(interp, fr, *a):
    _args("not", a, 1, 1)
    x = _n(a[0], "not")
    return -1 if x == 0 else 0


# ---- strings ----
@builtin("val")
def _val(interp, fr, *a):
    _args("val", a, 1, 1)
    return val(_s(a[0], "val"))


@builtin("str$")
def _str(interp, fr, *a):
    _args("str$", a, 1, 1)
    return fmt_num(_n(a[0], "str$"))


@builtin("len")
def _len(interp, fr, *a):
    _args("len", a, 1, 1)
    return len(to_str(a[0]))


@builtin("left$")
def _left(interp, fr, *a):
    _args("left$", a, 2, 2)
    n = int(_n(a[1], "left$"))
    return _s(a[0], "left$")[:max(n, 0)]


@builtin("right$")
def _right(interp, fr, *a):
    _args("right$", a, 2, 2)
    s = _s(a[0], "right$")
    n = int(_n(a[1], "right$"))
    if n <= 0:
        return ""
    return s[-n:]


@builtin("mid$")
def _mid(interp, fr, *a):
    _args("mid$", a, 2, 3)
    s = _s(a[0], "mid$")
    start = int(_n(a[1], "mid$"))
    if start < 1:
        start = 1
    if len(a) == 3:
        n = int(_n(a[2], "mid$"))
        if n <= 0:
            return ""
        return s[start - 1:start - 1 + n]
    return s[start - 1:]


@builtin("instr")
def _instr(interp, fr, *a):
    _args("instr", a, 2, 3)
    s, t = _s(a[0], "instr"), _s(a[1], "instr")
    start = int(_n(a[2], "instr")) if len(a) == 3 else 1
    if start < 1:
        start = 1
    if t == "":
        return 0
    return s.find(t, start - 1) + 1


@builtin("upper$")
def _upper(interp, fr, *a):
    _args("upper$", a, 1, 1)
    return _s(a[0], "upper$").upper()


@builtin("lower$")
def _lower(interp, fr, *a):
    _args("lower$", a, 1, 1)
    return _s(a[0], "lower$").lower()


@builtin("trim$")
def _trim(interp, fr, *a):
    _args("trim$", a, 1, 1)
    return _s(a[0], "trim$").strip(" \t\r\n\0")


@builtin("space$")
def _space(interp, fr, *a):
    _args("space$", a, 1, 1)
    return " " * max(0, int(_n(a[0], "space$")))


@builtin("chr$")
def _chr(interp, fr, *a):
    _args("chr$", a, 1, 1)
    n = int(_n(a[0], "chr$"))
    if n < 0 or n > 0x10FFFF:
        raise BasicError(f"chr$({n}) is out of range")
    return chr(n)


@builtin("asc")
def _asc(interp, fr, *a):
    _args("asc", a, 1, 1)
    s = _s(a[0], "asc")
    return ord(s[0]) if s else 0


@builtin("word$")
def _word(interp, fr, *a):
    _args("word$", a, 2, 3)
    s = _s(a[0], "word$")
    n = int(_n(a[1], "word$"))
    if len(a) == 3:
        parts = s.split(_s(a[2], "word$")) if a[2] else [s]
    else:
        parts = s.split()
    if 1 <= n <= len(parts):
        return parts[n - 1]
    return ""


@builtin("tab")
def _tab(interp, fr, *a):
    _args("tab", a, 1, 1)
    return TabMarker(_n(a[0], "tab"))


@builtin("using")
def _using(interp, fr, *a):
    _args("using", a, 2, 2)
    tmpl = _s(a[0], "using")
    x = _n(a[1], "using")
    if "." in tmpl:
        whole, frac = tmpl.split(".", 1)
        decimals = sum(1 for c in frac if c == "#")
    else:
        whole, decimals = tmpl, 0
    commas = "," in whole
    s = f"{x:,.{decimals}f}" if commas else f"{x:.{decimals}f}"
    width = len(tmpl)
    if len(s) > width:
        return "%" + s
    return s.rjust(width)


@builtin("hexdec")
def _hexdec(interp, fr, *a):
    _args("hexdec", a, 1, 1)
    s = _s(a[0], "hexdec").strip()
    if s.lower().startswith("&h"):
        s = s[2:]
    try:
        return int(s, 16) if s else 0
    except ValueError:
        return 0


@builtin("dechex$")
def _dechex(interp, fr, *a):
    _args("dechex$", a, 1, 1)
    return format(int(_n(a[0], "dechex$")) & 0xFFFFFFFF if a[0] < 0 else int(a[0]), "X")


# ---- date and time ----
@builtin("date$")
def _date(interp, fr, *a):
    now = datetime.date.today()
    if not a:
        return now.strftime("%b %d, %Y")
    fmt = _s(a[0], "date$").strip()
    low = fmt.lower()
    if low == "mm/dd/yyyy":
        return now.strftime("%m/%d/%Y")
    if low == "mm/dd/yy":
        return now.strftime("%m/%d/%y")
    if low == "yyyy/mm/dd":
        return now.strftime("%Y/%m/%d")
    if low == "days":
        return (now - datetime.date(1901, 1, 1)).days
    # a date string -> days since 1/1/1901
    for f in ("%m/%d/%Y", "%m/%d/%y", "%b %d, %Y", "%Y/%m/%d", "%B %d, %Y"):
        try:
            d = datetime.datetime.strptime(fmt, f).date()
            return (d - datetime.date(1901, 1, 1)).days
        except ValueError:
            pass
    # a number of days -> date string
    try:
        days = int(float(fmt))
        d = datetime.date(1901, 1, 1) + datetime.timedelta(days=days)
        return d.strftime("%m/%d/%Y")
    except ValueError:
        raise BasicError(f'date$("{fmt}") is not a format I know')


@builtin("time$")
def _time(interp, fr, *a):
    now = datetime.datetime.now()
    if not a:
        return now.strftime("%H:%M:%S")
    fmt = _s(a[0], "time$").strip().lower()
    midnight = now.replace(hour=0, minute=0, second=0, microsecond=0)
    if fmt == "seconds":
        return int((now - midnight).total_seconds())
    if fmt in ("milliseconds", "ms"):
        return int((now - midnight).total_seconds() * 1000)
    return now.strftime("%H:%M:%S")


# ---- files ----
@builtin("eof", handles=True)
def _eof(interp, fr, *a):
    _args("eof", a, 1, 1)
    return interp.file(a[0]).eof()


@builtin("lof", handles=True)
def _lof(interp, fr, *a):
    _args("lof", a, 1, 1)
    return interp.file(a[0]).lof()


@builtin("loc", handles=True)
def _loc(interp, fr, *a):
    _args("loc", a, 1, 1)
    return interp.file(a[0]).loc()


@builtin("input$", handles=True)
def _input(interp, fr, *a):
    _args("input$", a, 1, 2)
    if len(a) == 2:
        return interp.file(a[0]).read_chars(int(_n(a[1], "input$")))
    # input$(n): read n keys from the keyboard (mainwin)
    return interp.host.console_read_chars(int(_n(a[0], "input$")))


@builtin("hwnd", handles=True)
def _hwnd(interp, fr, *a):
    _args("hwnd", a, 1, 1)
    return interp.host.hwnd(a[0])


@builtin("mkdir")
def _mkdir(interp, fr, *a):
    _args("mkdir", a, 1, 1)
    try:
        os.mkdir(interp.resolve(_s(a[0], "mkdir"), must_exist=False))
        return 0
    except FileExistsError:
        return 183
    except OSError as e:
        return e.errno or 1


@builtin("rmdir")
def _rmdir(interp, fr, *a):
    _args("rmdir", a, 1, 1)
    try:
        os.rmdir(interp.resolve(_s(a[0], "rmdir")))
        return 0
    except OSError as e:
        return e.errno or 1


@builtin("midipos")
def _midipos(interp, fr, *a):
    return interp.host.midipos()


# ---- eval ----
def _eval_impl(interp, fr, expr):
    from .parser import Parser
    f = interp.eval_cache.get((fr.unit.name, expr))
    if f is None:
        p = Parser(expr)
        node = p.expr()
        if p.peek().k not in ("nl", "eof"):
            raise BasicError(f"eval(): can't understand '{expr}'")
        saved = getattr(interp, "cu", None)
        interp.cu = fr.unit
        try:
            f = interp.cexpr(node)
        finally:
            interp.cu = saved
        interp.eval_cache[(fr.unit.name, expr)] = f
    return f(fr)


@builtin("eval")
def _eval(interp, fr, *a):
    _args("eval", a, 1, 1)
    r = _eval_impl(interp, fr, _s(a[0], "eval"))
    return val(r) if isinstance(r, str) else r


@builtin("eval$")
def _evals(interp, fr, *a):
    _args("eval$", a, 1, 1)
    return to_str(_eval_impl(interp, fr, _s(a[0], "eval$")))

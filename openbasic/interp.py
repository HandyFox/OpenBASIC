"""Compiler and interpreter for Just BASIC programs.

The parser output is compiled into flat lists of operations (one list per
program, SUB and FUNCTION). Each operation is a Python closure; control flow
is expressed as jumps. Expressions are compiled into closures too, which keeps
the interpreter reasonably fast while staying easy to read and debug.

All windowing, dialogs and sound go through a *host* object (see
host_base.Host). The Qt runtime implements a real host; tests use a
headless one.
"""
import math
import os
import random
import shutil
import sys
import time
import datetime

from .errors import BasicError, BasicSyntaxError, EndProgram, StopRequested
from .fileio import BFile, read_value
from .parser import Parser, S, parse
from . import paths
from .values import BArray, TabMarker, fmt_num, normalize_num, to_str, val

VERSION = "1.0"

RETURN = object()  # sentinel returned by ops that leave a SUB/FUNCTION

# System variables are shared by every SUB and their names are not case sensitive.
SYSVARS = [
    "WindowWidth", "WindowHeight", "UpperLeftX", "UpperLeftY",
    "DisplayWidth", "DisplayHeight", "DefaultDir$", "StartupDir$", "Platform$",
    "Version$", "Drives$", "CommandLine$", "Inkey$", "MouseX", "MouseY",
    "BackgroundColor$", "ForegroundColor$", "TextboxColor$", "ListboxColor$",
    "ComboboxColor$", "TexteditorColor$", "Err", "Err$", "ProgramName$",
]
SYS_CANON = {n.lower(): n for n in SYSVARS}


class Event:
    __slots__ = ("handler", "args", "vars", "handle")

    def __init__(self, handler, args=(), vars=None, handle=None):
        self.handler = handler  # ('label', name) or ('sub', name)
        self.args = list(args)
        self.vars = vars or {}
        self.handle = handle


class Op:
    __slots__ = ("fn", "line", "first")

    def __init__(self, fn, line, first):
        self.fn = fn
        self.line = line
        self.first = first


class Target:
    __slots__ = ("pc",)

    def __init__(self, pc=None):
        self.pc = pc


class Unit:
    def __init__(self, name, kind, params=(), line=0):
        self.name = name
        self.kind = kind  # 'main', 'sub', 'function'
        self.params = list(params)
        self.code = []
        self.labels = {}
        self.label_lines = {}
        self.line = line


class Frame:
    __slots__ = ("unit", "vars", "pc", "gosub", "loops", "sel")

    def __init__(self, unit, vars):
        self.unit = unit
        self.vars = vars
        self.pc = 0
        self.gosub = []
        self.loops = {}
        self.sel = {}


class Debugger:
    """State for breakpoints and stepping. The host does the UI part."""

    def __init__(self):
        self.breakpoints = set()
        self.mode = "run"  # run | step | over | out | animate
        self.target_depth = 0
        self.pause_requested = False


def _type_name(v):
    return "string" if isinstance(v, str) else "number"


class Interpreter:
    def __init__(self, source, host, filename=None, debugger=None, argv=""):
        self.source = source
        self.host = host
        self.filename = filename
        self.base_dir = os.path.dirname(os.path.abspath(filename)) if filename else os.getcwd()
        self.debugger = debugger
        self.gvars = {}
        self.arrays = {}
        self.files = {}
        self.frames = []
        self.units = {}
        self.functions = {}
        self.global_names = set()
        self.data = []
        self.data_labels = {}
        self.data_pos = 0
        self.eval_cache = {}
        self.op_count = 0
        self.current_line = 0
        self.mainwin = True
        self.dll_handles = {}
        self.gui_replies = {}
        self.error_label = None
        self.ended = False
        self._init_sysvars(argv)
        self.compile()

    # ------------------------------------------------------------------ setup
    def _init_sysvars(self, argv):
        g = self.gvars
        g["WindowWidth"] = 320
        g["WindowHeight"] = 360
        g["UpperLeftX"] = 0
        g["UpperLeftY"] = 0
        try:
            dw, dh = self.host.display_size()
        except Exception:
            dw, dh = 1024, 768
        g["DisplayWidth"] = dw
        g["DisplayHeight"] = dh
        g["DefaultDir$"] = self.base_dir
        g["StartupDir$"] = self.base_dir
        g["Platform$"] = {"win32": "Windows", "darwin": "Mac"}.get(sys.platform, "Linux")
        g["Version$"] = f"OpenBASIC {VERSION}"
        g["Drives$"] = self._drives()
        g["CommandLine$"] = argv
        g["Inkey$"] = ""
        g["MouseX"] = 0
        g["MouseY"] = 0
        for n in ("BackgroundColor$", "ForegroundColor$", "TextboxColor$", "ListboxColor$",
                  "ComboboxColor$", "TexteditorColor$"):
            g[n] = ""
        g["Err"] = 0
        g["Err$"] = ""
        g["ProgramName$"] = os.path.basename(self.filename) if self.filename else "untitled.bas"

    @staticmethod
    def _drives():
        if os.name == "nt":
            import string
            return " ".join(f"{d}:" for d in string.ascii_uppercase if os.path.exists(f"{d}:\\"))
        return "/"

    # --------------------------------------------------------------- compile
    def compile(self):
        stmts = parse(self.source)
        main_stmts = []
        sub_defs = []
        cur = main_stmts
        cur_def = None
        for st in stmts:
            if st.kind in ("sub", "function"):
                if cur_def is not None:
                    raise BasicSyntaxError(
                        f"{cur_def.kind.upper()} {cur_def.name} is missing END {cur_def.kind.upper()}", st.line)
                cur_def = st
                cur = []
                sub_defs.append((st, cur))
            elif st.kind in ("endsub", "endfunction"):
                if cur_def is None or ("end" + cur_def.kind) != st.kind:
                    raise BasicSyntaxError(f"{st.kind.replace('end', 'END ').upper()} without a matching start", st.line)
                cur_def = None
                cur = main_stmts
            else:
                cur.append(st)
        if cur_def is not None:
            raise BasicSyntaxError(f"{cur_def.kind.upper()} {cur_def.name} is missing END {cur_def.kind.upper()}", cur_def.line)

        # pre-pass: globals, data, sub/function names
        def walk(sts):
            for st in sts:
                yield st
                if st.kind == "if1":
                    yield from walk(st.then)
                    yield from walk(st.els)
        all_lists = [main_stmts] + [b for _, b in sub_defs]
        for body in all_lists:
            for st in walk(body):
                if st.kind == "global":
                    for n in st.names:
                        self.global_names.add(self.canon_static(n))
        # DATA in source order
        ordered = sorted([st for body in all_lists for st in walk(body)], key=lambda s: s.line)
        for st in ordered:
            if st.kind == "label":
                self.data_labels.setdefault(st.name, len(self.data))
            elif st.kind == "data":
                self.data.extend(st.values)

        for d, body in sub_defs:
            key = d.name.lower()
            if key in self.units:
                raise BasicSyntaxError(f"{d.kind.upper()} {d.name} is defined twice", d.line)
            u = Unit(d.name, d.kind, d.params, d.line)
            self.units[key] = u
            if d.kind == "function":
                self.functions[key] = u

        self.main = Unit("(main)", "main")
        self._compile_unit(self.main, main_stmts)
        for d, body in sub_defs:
            self._compile_unit(self.units[d.name.lower()], body)

    def canon_static(self, name):
        c = SYS_CANON.get(name.lower())
        return c or name

    def canon(self, name):
        c = SYS_CANON.get(name.lower())
        if c:
            return c
        u = self.cu
        if u.kind == "function" and name.lower() == u.name.lower():
            return u.name
        return name

    # ---- unit compiler ----
    def _compile_unit(self, unit, stmts):
        self.cu = unit
        self.code = unit.code
        self.blocks = []
        self.pending_labels = []  # (name, line) gotos to verify
        for st in stmts:
            self._stmt(st)
        if self.blocks:
            b = self.blocks[-1]
            names = {"if": "END IF", "for": "NEXT", "while": "WEND", "do": "LOOP", "select": "END SELECT"}
            raise BasicSyntaxError(f"{b['kind'].upper()} without {names[b['kind']]}", b["line"])
        if unit.kind != "main":
            self.emit(lambda fr: RETURN, unit.line, True)
        for name, line in self.pending_labels:
            if name not in unit.labels:
                where = "" if unit.kind == "main" else f" inside {unit.kind.upper()} {unit.name}"
                raise BasicSyntaxError(f"Branch label [{name}] not found{where}", line)

    def emit(self, fn, line, first=False):
        self.code.append(Op(fn, line, first))
        return len(self.code) - 1

    def here(self):
        return len(self.code)

    def _stmt(self, st):
        m = getattr(self, "c_" + st.kind, None)
        if m is None:
            raise BasicSyntaxError(f"Unsupported statement '{st.kind}'", st.line)
        start = len(self.code)
        m(st)
        if len(self.code) > start:
            self.code[start].first = True

    # ---------------------------------------------------------- expressions
    def cexpr(self, node):
        k = node[0]
        if k == "num":
            v = node[1]
            return lambda fr: v
        if k == "str":
            v = node[1]
            return lambda fr: v
        if k == "var":
            return self.cvar_get(node[1])
        if k == "handle":
            h = self.chandle(node)
            return h
        if k == "un":
            f = self.cexpr(node[2])
            if node[1] == "-":
                def neg(fr):
                    v = f(fr)
                    if isinstance(v, str):
                        raise BasicError("Can't make a string negative")
                    return -v
                return neg
            return lambda fr: _not(f(fr))
        if k == "bin":
            return self.cbin(node)
        if k == "call":
            return self.ccall(node)
        raise BasicError(f"Bad expression node {k}")

    def cbin(self, node):
        op, l, r = node[1], self.cexpr(node[2]), self.cexpr(node[3])
        if op == "+":
            def add(fr):
                a, b = l(fr), r(fr)
                if type(a) is type(b) or not (isinstance(a, str) or isinstance(b, str)):
                    try:
                        return a + b
                    except TypeError:
                        pass
                raise BasicError(f"Type mismatch: can't add a {_type_name(a)} to a {_type_name(b)} "
                                 f"(use str$() or val() to convert)")
            return add
        if op == "-":
            return lambda fr: _num_op(l(fr), r(fr), "-", lambda a, b: a - b)
        if op == "*":
            return lambda fr: _num_op(l(fr), r(fr), "*", lambda a, b: a * b)
        if op == "/":
            def div(fr):
                a, b = l(fr), r(fr)
                _check_nums(a, b, "/")
                if b == 0:
                    raise BasicError("Division by zero")
                if isinstance(a, int) and isinstance(b, int) and a % b == 0:
                    return a // b
                return a / b
            return div
        if op == "^":
            def pw(fr):
                a, b = l(fr), r(fr)
                _check_nums(a, b, "^")
                try:
                    if isinstance(a, int) and isinstance(b, int) and 0 <= b <= 4096:
                        return a ** b
                    res = float(a) ** float(b)
                    if isinstance(res, complex):
                        raise BasicError("Can't raise a negative number to a fractional power")
                    return res
                except OverflowError:
                    raise BasicError("Number too large")
                except ZeroDivisionError:
                    raise BasicError("Division by zero")
            return pw
        if op == "mod":
            def md(fr):
                a, b = l(fr), r(fr)
                _check_nums(a, b, "MOD")
                if b == 0:
                    raise BasicError("Division by zero in MOD")
                return normalize_num(math.fmod(a, b)) if (isinstance(a, float) or isinstance(b, float)) else int(math.fmod(a, b))
            return md
        if op in ("=", "<>", "<", ">", "<=", ">="):
            import operator
            f = {"=": operator.eq, "<>": operator.ne, "<": operator.lt, ">": operator.gt,
                 "<=": operator.le, ">=": operator.ge}[op]

            def cmp(fr):
                a, b = l(fr), r(fr)
                if isinstance(a, str) != isinstance(b, str):
                    raise BasicError(f"Type mismatch: can't compare a {_type_name(a)} with a {_type_name(b)}")
                return 1 if f(a, b) else 0
            return cmp
        if op in ("and", "or", "xor"):
            import operator
            f = {"and": operator.and_, "or": operator.or_, "xor": operator.xor}[op]

            def logic(fr):
                a, b = l(fr), r(fr)
                _check_nums(a, b, op.upper())
                return f(int(a), int(b))
            return logic
        raise BasicError(f"Unknown operator {op}")

    # ---- variables ----
    def cvar_get(self, name):
        name = self.canon(name)
        default = "" if name.endswith("$") else 0
        if self.cu.kind == "main" or name in self.global_names or name in SYS_CANON.values():
            g = self.gvars
            return lambda fr: g.get(name, default)
        return lambda fr: fr.vars.get(name, default)

    def cvar_set(self, name):
        name = self.canon(name)
        is_str = name.endswith("$")
        use_global = self.cu.kind == "main" or name in self.global_names or name in SYS_CANON.values()
        g = self.gvars

        def setter(fr, v):
            if is_str:
                if not isinstance(v, str):
                    if isinstance(v, TabMarker):
                        v = ""
                    else:
                        raise BasicError(f"Type mismatch: can't put a number into string variable {name}")
            else:
                if isinstance(v, str):
                    raise BasicError(f"Type mismatch: can't put a string into number variable {name} "
                                     f"(use val() to convert)")
                if isinstance(v, bool):
                    v = int(v)
            (g if use_global else fr.vars)[name] = v
        return setter

    def set_var_dynamic(self, fr, name, v):
        """Assign by name at run time (used for GUI '?' queries)."""
        name = SYS_CANON.get(name.lower(), name)
        u = fr.unit
        if u.kind == "function" and name.lower() == u.name.lower():
            name = u.name
        if name.endswith("$"):
            v = v if isinstance(v, str) else to_str(v)
        else:
            if isinstance(v, str):
                v = val(v)
        if u.kind == "main" or name in self.global_names or name in SYS_CANON.values():
            self.gvars[name] = v
        else:
            fr.vars[name] = v

    def get_var_dynamic(self, fr, name):
        name = SYS_CANON.get(name.lower(), name)
        default = "" if name.endswith("$") else 0
        u = fr.unit
        if u.kind == "main" or name in self.global_names:
            return self.gvars.get(name, default)
        return fr.vars.get(name, default)

    def get_array(self, name, ndims=1):
        a = self.arrays.get(name)
        if a is None:
            a = BArray(name, [10] * ndims)
            self.arrays[name] = a
        return a

    def clvalue(self, node):
        """Return a setter closure (fr, value)."""
        if node[0] == "var":
            return self.cvar_set(node[1])
        if node[0] == "call":
            name = node[1]
            if name.lower() in self.functions:
                raise BasicError(f"Can't assign to function {name}()")
            idx = [self.cexpr(a) for a in node[2]]
            is_str = name.endswith("$")
            interp = self

            def aset(fr, v):
                if is_str and not isinstance(v, str):
                    raise BasicError(f"Type mismatch: can't put a number into string array {name}()")
                if not is_str and isinstance(v, str):
                    raise BasicError(f"Type mismatch: can't put a string into number array {name}()")
                interp.get_array(name, len(idx)).set([_num(i(fr), "array index") for i in idx], v)
            return aset
        raise BasicError("Expected a variable")

    def chandle(self, node):
        name = node[1]
        if "$" in name:
            # #handle$ or #handle$.extension: the handle comes from a string variable
            var, ext = name[1:name.index("$") + 1], name[name.index("$") + 1:]
            getter = self.cvar_get(var)

            def dyn(fr):
                s = str(getter(fr)).strip()
                if not s:
                    raise BasicError(f"Handle variable {var} is empty")
                if not s.startswith("#"):
                    s = "#" + s
                return (s + ext).lower()
            return dyn
        key = name.lower()
        return lambda fr: key

    # ---- calls ----
    def ccall(self, node):
        name, args = node[1], node[2]
        lname = name.lower()
        if lname in self.functions:
            return self.cuser_call(self.functions[lname], args, node)
        b = BUILTINS.get(lname)
        if b is not None and name not in self.arrays_declared():
            fn, raw = b
            if raw:
                cargs = [self.chandle(a) if a[0] == "handle" else self.cexpr(a) for a in args]
            else:
                cargs = [self.cexpr(a) for a in args]
            interp = self
            if len(cargs) == 1:
                a0 = cargs[0]
                return lambda fr: fn(interp, fr, a0(fr))
            if len(cargs) == 0:
                return lambda fr: fn(interp, fr)
            return lambda fr: fn(interp, fr, *[c(fr) for c in cargs])
        # array element
        idx = [self.cexpr(a) for a in args]
        if not idx:
            raise BasicError(f"{name}() needs an index (or is an unknown function)")
        interp = self
        if len(idx) == 1:
            i0 = idx[0]
            return lambda fr: interp.get_array(name, 1).get((_num(i0(fr), "array index"),))
        return lambda fr: interp.get_array(name, len(idx)).get([_num(i(fr), "array index") for i in idx])

    def arrays_declared(self):
        return ()

    def cuser_call(self, unit, args, node):
        cargs = [self.chandle(a) if a[0] == "handle" else self.cexpr(a) for a in args]
        setters = []
        for i, a in enumerate(args):
            if a[0] in ("var",) or (a[0] == "call" and a[1].lower() not in self.functions
                                    and a[1].lower() not in BUILTINS and a[2]):
                try:
                    setters.append(self.clvalue(a))
                except BasicError:
                    setters.append(None)
            else:
                setters.append(None)
        interp = self

        def call(fr):
            return interp.invoke(unit, [c(fr) for c in cargs], setters, fr)
        return call

    def invoke(self, unit, values, setters, caller):
        ps = unit.params
        if len(values) != len(ps):
            raise BasicError(f"{unit.kind.upper()} {unit.name} expects {len(ps)} argument(s) but got {len(values)}")
        fr = Frame(unit, {})
        for (pname, byref), v in zip(ps, values):
            pname_c = SYS_CANON.get(pname.lower(), pname)
            if pname.endswith("$"):
                if not isinstance(v, str):
                    raise BasicError(f"{unit.name}: parameter {pname} needs a string")
            else:
                if isinstance(v, str):
                    raise BasicError(f"{unit.name}: parameter {pname} needs a number")
            fr.vars[pname_c] = v
        if len(self.frames) > 2000:
            raise BasicError("Too many nested calls (runaway recursion?)")
        self.frames.append(fr)
        try:
            self.run_frame(fr)
        finally:
            self.frames.pop()
        for (pname, byref), s in zip(ps, setters or [None] * len(ps)):
            if byref and s is not None:
                s(caller, fr.vars.get(pname, "" if pname.endswith("$") else 0))
        if unit.kind == "function":
            default = "" if unit.name.endswith("$") else 0
            return fr.vars.get(unit.name, default)
        return None

    def call_sub_by_name(self, name, args, fr):
        unit = self.units.get(name.lower())
        if unit is None or unit.kind != "sub":
            raise BasicError(f"SUB {name} not found")
        args = list(args)[:len(unit.params)]
        while len(args) < len(unit.params):
            p = unit.params[len(args)][0]
            args.append("" if p.endswith("$") else 0)
        fixed = []
        for (p, _), a in zip(unit.params, args):
            if p.endswith("$"):
                fixed.append(a if isinstance(a, str) else to_str(a))
            else:
                fixed.append(val(a) if isinstance(a, str) else a)
        self.invoke(unit, fixed, None, fr)

    # ------------------------------------------------------- statements
    def c_label(self, st):
        if st.name in self.cu.labels:
            raise BasicSyntaxError(f"Branch label [{st.name}] is defined twice "
                                   f"(also on line {self.cu.label_lines[st.name]})", st.line)
        self.cu.labels[st.name] = self.here()
        self.cu.label_lines[st.name] = st.line

    def c_assign(self, st):
        e = self.cexpr(st.expr)
        s = self.clvalue(st.target)

        def op(fr):
            s(fr, e(fr))
        self.emit(op, st.line)

    def c_print(self, st):
        parts = []
        for it in st.items:
            if it[0] == "sep":
                parts.append(("sep", it[1]))
            else:
                parts.append(("e", self.cexpr(it[1])))
        newline = not (parts and parts[-1][0] == "sep")
        h = self.chandle(st.handle) if st.handle else None
        interp = self

        def build(fr, start_col):
            out = []
            col = start_col
            for kind, x in parts:
                if kind == "sep":
                    if x == ",":
                        pad = 14 - (col % 14)
                        out.append(" " * pad)
                        col += pad
                    continue
                v = x(fr)
                if isinstance(v, TabMarker):
                    target = int(v.col) - 1
                    if target > col:
                        out.append(" " * (target - col))
                        col = target
                    continue
                s = v if isinstance(v, str) else fmt_num(v)
                out.append(s)
                nl = s.rfind("\n")
                col = len(s) - nl - 1 if nl >= 0 else col + len(s)
            return "".join(out)

        if h is None:
            def op(fr):
                text = build(fr, interp.host.console_col())
                interp.host.console_write(text + ("\n" if newline else ""))
        else:
            def op(fr):
                key = h(fr)
                f = interp.files.get(key)
                if f is not None:
                    text = build(fr, f.col)
                    f.write(text + ("\n" if newline else ""))
                    return
                text = build(fr, 0)
                interp.gui_command(fr, key, text, newline)
        self.emit(op, st.line)

    def gui_command(self, fr, key, text, newline=True):
        if not self.host.is_gui_handle(key):
            raise BasicError(f"Handle {key} is not open")
        text = _add_reply_slots(text)
        result = self.host.gui_print(key, text, newline)
        if result:
            for name, v in result.items():
                if name.startswith("__reply"):
                    # answer to a query like "!contents?" without a variable;
                    # the program reads it with INPUT #handle, var$
                    self.gui_replies.setdefault(key, []).append(v)
                else:
                    self.set_var_dynamic(fr, name, v)

    def c_lprint(self, st):
        st2 = S("print", st.line, handle=None, items=st.items)
        self.c_print(st2)

    def c_input(self, st):
        setters = [(self.clvalue(t), t[1].endswith("$")) for t in st.targets]
        interp = self
        if st.handle:
            h = self.chandle(st.handle)

            def op(fr):
                key = h(fr)
                f = interp.files.get(key)
                if f is None:
                    if interp.host.is_gui_handle(key) or key in interp.gui_replies:
                        replies = interp.gui_replies.get(key)
                        if not replies:
                            # Old-style event loop: INPUT #window, r$ waits for events
                            return interp.do_wait(fr)
                        for s, is_str in setters:
                            v = replies.pop(0) if replies else ("" if is_str else 0)
                            s(fr, v if is_str == isinstance(v, str) else (to_str(v) if is_str else val(v)))
                        return None
                    raise BasicError(f"File {key} is not open")
                for s, is_str in setters:
                    item = f.read_line() if st.whole_line else f.read_item()
                    s(fr, read_value(item, is_str))
            self.emit(op, st.line)
            return
        prompt = st.prompt
        pf = None
        if isinstance(prompt, tuple):
            pf = self.cexpr(prompt)

        def op(fr):
            p = prompt if isinstance(prompt, str) else (to_str(pf(fr)) if pf else "?")
            if len(setters) == 1 or st.whole_line:
                text = interp.host.console_input(p)
                s, is_str = setters[0]
                s(fr, text if is_str else val(text))
            else:
                text = interp.host.console_input(p)
                pieces = text.split(",")
                for i, (s, is_str) in enumerate(setters):
                    piece = pieces[i].strip() if i < len(pieces) else ""
                    s(fr, piece if is_str else val(piece))
        self.emit(op, st.line)

    # ---- IF ----
    def _jf(self, cond, line):
        t = Target()
        c = self.cexpr(cond)

        def op(fr):
            v = c(fr)
            if isinstance(v, str):
                raise BasicError("IF needs a comparison or number, not a string")
            if not v:
                return t.pc
        self.emit(op, line)
        return t

    def _jmp(self, line, t=None):
        t = t or Target()
        self.emit(lambda fr: t.pc, line)
        return t

    def c_if1(self, st):
        jf = self._jf(st.cond, st.line)
        for s in st.then:
            self._stmt(s)
        if st.els:
            end = self._jmp(st.line)
            jf.pc = self.here()
            for s in st.els:
                self._stmt(s)
            end.pc = self.here()
        else:
            jf.pc = self.here()

    def c_if(self, st):
        jf = self._jf(st.cond, st.line)
        self.blocks.append({"kind": "if", "line": st.line, "jf": jf, "ends": [], "else": False})

    def _top(self, kind, st, what):
        if not self.blocks or self.blocks[-1]["kind"] != kind:
            if self.blocks:
                b = self.blocks[-1]
                raise BasicSyntaxError(f"{what} found but the {b['kind'].upper()} on line {b['line']} isn't finished", st.line)
            raise BasicSyntaxError(f"{what} without a matching {kind.upper()}", st.line)
        return self.blocks[-1]

    def c_elseif(self, st):
        b = self._top("if", st, "ELSEIF")
        if b["else"]:
            raise BasicSyntaxError("ELSEIF after ELSE", st.line)
        b["ends"].append(self._jmp(st.line))
        b["jf"].pc = self.here()
        b["jf"] = self._jf(st.cond, st.line)

    def c_else(self, st):
        b = self._top("if", st, "ELSE")
        if b["else"]:
            raise BasicSyntaxError("Two ELSEs in one IF", st.line)
        b["ends"].append(self._jmp(st.line))
        b["jf"].pc = self.here()
        b["jf"] = None
        b["else"] = True

    def c_endif(self, st):
        b = self._top("if", st, "END IF")
        self.blocks.pop()
        if b["jf"] is not None:
            b["jf"].pc = self.here()
        for t in b["ends"]:
            t.pc = self.here()

    # ---- loops ----
    def c_for(self, st):
        getv = self.cvar_get(st.var)
        setv = self.cvar_set(st.var)
        start = self.cexpr(st.start)
        end = self.cexpr(st.end)
        step = self.cexpr(st.step) if st.step else (lambda fr: 1)
        exit_t = Target()
        key = object()

        def op(fr):
            s, e, stp = start(fr), end(fr), step(fr)
            _check_nums(s, e, "FOR")
            _check_nums(stp, 0, "STEP")
            setv(fr, s)
            fr.loops[key] = (e, stp)
            if (stp >= 0 and s > e) or (stp < 0 and s < e):
                return exit_t.pc
        pc = self.emit(op, st.line)
        self.blocks.append({"kind": "for", "line": st.line, "var": st.var, "start": pc + 1,
                            "exit": exit_t, "key": key, "getv": getv, "setv": setv})

    def c_next(self, st):
        b = self._top("for", st, "NEXT")
        if st.var and st.var.lower() != b["var"].lower():
            raise BasicSyntaxError(f"NEXT {st.var} doesn't match FOR {b['var']} on line {b['line']}", st.line)
        self.blocks.pop()
        key, getv, setv, body = b["key"], b["getv"], b["setv"], b["start"]

        def op(fr):
            e, stp = fr.loops[key]
            v = getv(fr) + stp
            if isinstance(v, float):
                v = normalize_num(round(v, 12))
            setv(fr, v)
            if (stp >= 0 and v <= e) or (stp < 0 and v >= e):
                return body
        self.emit(op, st.line)
        b["exit"].pc = self.here()

    def c_while(self, st):
        start = self.here()
        jf = self._jf(st.cond, st.line)
        self.blocks.append({"kind": "while", "line": st.line, "start": start, "exit": jf})

    def c_wend(self, st):
        b = self._top("while", st, "WEND")
        self.blocks.pop()
        self._jmp(st.line, Target(b["start"]))
        b["exit"].pc = self.here()

    def c_do(self, st):
        start = self.here()
        exit_t = Target()
        if st.cond_kind:
            c = self.cexpr(st.cond)
            until = st.cond_kind == "until"

            def op(fr):
                v = c(fr)
                if bool(v) == until:
                    return exit_t.pc
            self.emit(op, st.line)
        else:
            self.emit(lambda fr: None, st.line)
        self.blocks.append({"kind": "do", "line": st.line, "start": start, "exit": exit_t})

    def c_loop(self, st):
        b = self._top("do", st, "LOOP")
        self.blocks.pop()
        start = b["start"]
        if st.cond_kind:
            c = self.cexpr(st.cond)
            until = st.cond_kind == "until"

            def op(fr):
                v = c(fr)
                if bool(v) != until:
                    return start
            self.emit(op, st.line)
        else:
            self._jmp(st.line, Target(start))
        b["exit"].pc = self.here()

    def c_exit(self, st):
        what = st.what
        if what in ("sub", "function"):
            if self.cu.kind != what:
                raise BasicSyntaxError(f"EXIT {what.upper()} outside a {what.upper()}", st.line)
            self.emit(lambda fr: RETURN, st.line)
            return
        kind = {"for": "for", "while": "while", "do": "do", "select": "select"}.get(what)
        if kind is None:
            raise BasicSyntaxError(f"Can't EXIT {what.upper()}", st.line)
        for b in reversed(self.blocks):
            if b["kind"] == kind:
                t = b["exit"] if kind != "select" else b["end"]
                if kind == "select":
                    tt = Target()
                    b["ends"].append(tt)
                    self._jmp(st.line, tt)
                else:
                    self._jmp(st.line, t)
                return
        raise BasicSyntaxError(f"EXIT {what.upper()} outside a {what.upper()} loop", st.line)

    # ---- SELECT CASE ----
    def c_select(self, st):
        key = object()
        sel = self.cexpr(st.expr) if st.expr else None

        def op(fr):
            fr.sel[key] = sel(fr) if sel else None
        self.emit(op, st.line)
        self.blocks.append({"kind": "select", "line": st.line, "key": key, "next": None,
                            "ends": [], "end": None, "seen_case": False, "else": False})

    def c_case(self, st):
        b = self._top("select", st, "CASE")
        if b["else"]:
            raise BasicSyntaxError("CASE after CASE ELSE", st.line)
        if b["seen_case"]:
            t = Target()
            b["ends"].append(t)
            self._jmp(st.line, t)
        if b["next"] is not None:
            b["next"].pc = self.here()
        b["seen_case"] = True
        key = b["key"]
        tests = []
        for it in st.items:
            if it[0] == "range":
                lo, hi = self.cexpr(it[1]), self.cexpr(it[2])
                tests.append(("range", lo, hi))
            else:
                node = it[1]
                if node[0] == "bin" and node[1] in ("=", "<>", "<", ">", "<=", ">="):
                    tests.append(("bool", self.cexpr(node), None))
                else:
                    tests.append(("eq", self.cexpr(node), None))
        nxt = Target()
        b["next"] = nxt

        def op(fr):
            v = fr.sel[key]
            for kind, a, c in tests:
                if kind == "bool":
                    if a(fr):
                        return None
                elif kind == "eq":
                    x = a(fr)
                    if v is None:
                        if x:
                            return None
                    elif isinstance(x, str) != isinstance(v, str):
                        raise BasicError("Type mismatch in CASE: comparing a string with a number")
                    elif x == v:
                        return None
                else:
                    if a(fr) <= v <= c(fr):
                        return None
            return nxt.pc
        self.emit(op, st.line)

    def c_caseelse(self, st):
        b = self._top("select", st, "CASE ELSE")
        if b["seen_case"]:
            t = Target()
            b["ends"].append(t)
            self._jmp(st.line, t)
        if b["next"] is not None:
            b["next"].pc = self.here()
            b["next"] = None
        b["seen_case"] = True
        b["else"] = True
        self.emit(lambda fr: None, st.line)

    def c_endselect(self, st):
        b = self._top("select", st, "END SELECT")
        self.blocks.pop()
        if b["next"] is not None:
            b["next"].pc = self.here()
        for t in b["ends"]:
            t.pc = self.here()

    # ---- jumps ----
    def c_goto(self, st):
        labels = self.cu.labels
        name = st.label
        self.pending_labels.append((name, st.line))
        self.emit(lambda fr: labels[name], st.line)

    def c_gosub(self, st):
        labels = self.cu.labels
        name = st.label
        self.pending_labels.append((name, st.line))

        def op(fr):
            if len(fr.gosub) > 10000:
                raise BasicError("Too many nested GOSUBs (is a RETURN missing?)")
            fr.gosub.append(fr.pc)
            return labels[name]
        self.emit(op, st.line)

    def c_return(self, st):
        interp = self

        def op(fr):
            if fr.gosub:
                return fr.gosub.pop()
            # RETURN without GOSUB: Just BASIC stops with an error. We treat it
            # like WAIT so event-driven programs keep working.
            return interp.do_wait(fr)
        self.emit(op, st.line)

    def c_multi(self, st):
        for sub in st.stmts:
            self._stmt(sub)

    def c_mainwin(self, st):
        args = [self.cexpr(a) for a in st.args]
        interp = self

        def op(fr):
            vals = [int(_num(a(fr), "MAINWIN size")) for a in args]
            if len(vals) >= 2 and hasattr(interp.host, "mainwin_size"):
                interp.host.mainwin_size(vals[0], vals[1])
        self.emit(op, st.line)

    def c_titlebar(self, st):
        e = self.cexpr(st.expr)
        interp = self

        def op(fr):
            if hasattr(interp.host, "set_console_title"):
                interp.host.set_console_title(to_str(e(fr)))
        self.emit(op, st.line)

    def c_onerror(self, st):
        interp = self
        label = st.label
        if label:
            self.pending_labels.append((label, st.line))
        unit = self.cu

        def op(fr):
            interp.error_label = (unit, label) if label else None
        self.emit(op, st.line)

    def c_ongoto(self, st):
        e = self.cexpr(st.expr)
        labels = self.cu.labels
        names = st.labels
        for n in names:
            self.pending_labels.append((n, st.line))
        gosub = st.gosub

        def op(fr):
            i = int(_num(e(fr), "ON"))
            if 1 <= i <= len(names):
                if gosub:
                    fr.gosub.append(fr.pc)
                return labels[names[i - 1]]
            return None
        self.emit(op, st.line)

    def c_end(self, st):
        def op(fr):
            raise EndProgram()
        self.emit(op, st.line)

    def c_call(self, st):
        unit = self.units.get(st.name.lower())
        if unit is None:
            raise BasicSyntaxError(f"SUB {st.name} not found", st.line)
        if unit.kind == "function":
            f = self.cuser_call(unit, st.args, None)
        else:
            f = self.cuser_call(unit, st.args, None)
        self.emit(lambda fr: (f(fr), None)[1], st.line)

    # ---- waiting and events ----
    def c_wait(self, st):
        interp = self
        self.emit(lambda fr: interp.do_wait(fr), st.line)

    def c_scan(self, st):
        interp = self

        def op(fr):
            interp.host.pump(force=True)
            ev = interp.host.poll_event()
            if ev is not None:
                return interp.dispatch(ev, fr)
        self.emit(op, st.line)

    def do_wait(self, fr):
        while True:
            ev = self.host.wait_event()
            if ev is None:
                raise EndProgram()
            target = self.dispatch(ev, fr)
            if target is not None:
                return target

    def dispatch(self, ev, fr):
        for k, v in ev.vars.items():
            self.gvars[k] = v
        kind, name = ev.handler
        if kind == "label":
            pc = fr.unit.labels.get(name.lower())
            if pc is None:
                where = "" if fr.unit.kind == "main" else f" (the program was waiting inside {fr.unit.kind.upper()} {fr.unit.name})"
                raise BasicError(f"Branch label [{name}] not found{where}")
            return pc
        self.call_sub_by_name(name, ev.args, fr)
        return None

    def c_timer(self, st):
        ms = self.cexpr(st.ms)
        handler = st.handler
        interp = self
        if handler and handler[0] == "label":
            self.pending_labels.append((handler[1], st.line))

        def op(fr):
            interp.host.set_timer(_num(ms(fr), "TIMER"), handler)
        self.emit(op, st.line)

    # ---- declarations ----
    def c_dim(self, st):
        decls = [(n, [self.cexpr(d) for d in dims]) for n, dims in st.decls]
        interp = self

        def op(fr):
            for n, dims in decls:
                if not dims:
                    continue
                vals = [_num(d(fr), "DIM size") for d in dims]
                a = interp.arrays.get(n)
                if a is None:
                    interp.arrays[n] = BArray(n, vals)
                else:
                    a.redim(vals)
        self.emit(op, st.line)

    c_redim = c_dim

    def c_global(self, st):
        inits = [(self.cvar_set(n), self.cexpr(e)) for n, e in st.inits]

        def op(fr):
            for s, e in inits:
                s(fr, e(fr))
        self.emit(op, st.line)

    def c_data(self, st):
        pass

    def c_read(self, st):
        setters = [(self.clvalue(t), t[1].endswith("$")) for t in st.targets]
        interp = self

        def op(fr):
            for s, is_str in setters:
                if interp.data_pos >= len(interp.data):
                    raise BasicError("READ past the end of the DATA")
                v = interp.data[interp.data_pos]
                interp.data_pos += 1
                if is_str:
                    v = v if isinstance(v, str) else fmt_num(v)
                elif isinstance(v, str):
                    v = val(v)
                s(fr, v)
        self.emit(op, st.line)

    def c_restore(self, st):
        interp = self
        label = st.label
        if label is not None and label not in self.data_labels:
            raise BasicSyntaxError(f"Branch label [{label}] not found", st.line)

        def op(fr):
            interp.data_pos = interp.data_labels[label] if label else 0
        self.emit(op, st.line)

    # ---- simple statements ----
    def c_cls(self, st):
        interp = self
        self.emit(lambda fr: interp.host.console_cls(), st.line)

    def c_nomainwin(self, st):
        interp = self

        def op(fr):
            interp.mainwin = False
            interp.host.nomainwin()
        self.emit(op, st.line)

    def c_beep(self, st):
        interp = self
        self.emit(lambda fr: interp.host.beep(), st.line)

    def c_randomize(self, st):
        e = self.cexpr(st.expr) if st.expr else None

        def op(fr):
            random.seed(e(fr) if e else None)
        self.emit(op, st.line)

    def c_locate(self, st):
        x, y = self.cexpr(st.x), self.cexpr(st.y)
        interp = self
        self.emit(lambda fr: interp.host.console_locate(int(x(fr)), int(y(fr))), st.line)

    def c_notice(self, st):
        e = self.cexpr(st.expr)
        interp = self
        self.emit(lambda fr: interp.host.notice(to_str(e(fr))), st.line)

    def c_confirm(self, st):
        e = self.cexpr(st.expr)
        s = self.clvalue(st.target)
        is_str = st.target[1].endswith("$")
        interp = self

        def op(fr):
            yes = interp.host.confirm(to_str(e(fr)))
            s(fr, ("yes" if yes else "no") if is_str else (1 if yes else 0))
        self.emit(op, st.line)

    def c_prompt(self, st):
        e = self.cexpr(st.expr)
        s = self.clvalue(st.target)
        g = self.cexpr(st.target)
        interp = self

        def op(fr):
            default = g(fr)
            r = interp.host.prompt(to_str(e(fr)), to_str(default))
            s(fr, r if r is not None else "")
        self.emit(op, st.line)

    def c_filedialog(self, st):
        t, tm = self.cexpr(st.title), self.cexpr(st.template)
        s = self.clvalue(st.target)
        interp = self

        def op(fr):
            r = interp.host.filedialog(to_str(t(fr)), to_str(tm(fr)), interp.gvars["DefaultDir$"])
            s(fr, r or "")
        self.emit(op, st.line)

    def c_colordialog(self, st):
        c = self.cexpr(st.color)
        s = self.clvalue(st.target)
        interp = self
        self.emit(lambda fr: s(fr, interp.host.colordialog(to_str(c(fr))) or ""), st.line)

    def c_fontdialog(self, st):
        c = self.cexpr(st.font)
        s = self.clvalue(st.target)
        interp = self
        self.emit(lambda fr: s(fr, interp.host.fontdialog(to_str(c(fr))) or ""), st.line)

    def c_run(self, st):
        c = self.cexpr(st.cmd)
        mode = st.mode
        interp = self
        self.emit(lambda fr: interp.host.run_command(to_str(c(fr)), mode, interp.gvars["DefaultDir$"]), st.line)

    def resolve(self, path, must_exist=True):
        return paths.resolve(path, self.gvars.get("DefaultDir$") or self.base_dir, must_exist)

    def c_loadbmp(self, st):
        n, p = self.cexpr(st.name), self.cexpr(st.path)
        interp = self

        def op(fr):
            path = to_str(p(fr))
            real = interp.resolve(path)
            if not os.path.exists(real):
                raise BasicError(f"Bitmap file not found: {path}")
            interp.host.load_bmp(to_str(n(fr)), real)
        self.emit(op, st.line)

    def c_unloadbmp(self, st):
        n = self.cexpr(st.name)
        interp = self
        self.emit(lambda fr: interp.host.unload_bmp(to_str(n(fr))), st.line)

    def c_playwave(self, st):
        f = self.cexpr(st.file)
        mode = st.mode
        mf = self.cexpr(mode) if isinstance(mode, tuple) else None
        interp = self

        def op(fr):
            name = to_str(f(fr))
            m = to_str(mf(fr)).lower() if mf else (mode or "async")
            if not name.strip():
                interp.host.playwave(None, m)
                return
            real = interp.resolve(name)
            if not os.path.exists(real):
                raise BasicError(f"Sound file not found: {name}")
            interp.host.playwave(real, m)
        self.emit(op, st.line)

    def c_playmidi(self, st):
        f, t = self.cexpr(st.file), self.cexpr(st.times)
        s = self.clvalue(st.target) if st.target else None
        interp = self

        def op(fr):
            real = interp.resolve(to_str(f(fr)))
            if not os.path.exists(real):
                raise BasicError(f"MIDI file not found: {to_str(f(fr))}")
            length = interp.host.playmidi(real, t(fr))
            if s:
                s(fr, length or 0)
        self.emit(op, st.line)

    def c_stopmidi(self, st):
        interp = self
        self.emit(lambda fr: interp.host.stopmidi(), st.line)

    def c_kill(self, st):
        f = self.cexpr(st.file)
        interp = self

        def op(fr):
            p = interp.resolve(to_str(f(fr)))
            try:
                os.remove(p)
            except FileNotFoundError:
                raise BasicError(f"KILL: file not found: {to_str(f(fr))}")
            except OSError as e:
                raise BasicError(f"KILL failed: {e.strerror}")
        self.emit(op, st.line)

    def c_name(self, st):
        a, b = self.cexpr(st.old), self.cexpr(st.new)
        interp = self

        def op(fr):
            src = interp.resolve(to_str(a(fr)))
            dst = interp.resolve(to_str(b(fr)), must_exist=False)
            try:
                os.rename(src, dst)
            except OSError as e:
                raise BasicError(f"NAME failed: {e.strerror}")
        self.emit(op, st.line)

    def c_files(self, st):
        p, s = self.cexpr(st.path), self.cexpr(st.spec)
        arr = st.array
        interp = self

        def op(fr):
            import fnmatch
            base = interp.resolve(to_str(p(fr)) or ".")
            spec = to_str(s(fr)) or "*.*"
            if spec in ("*.*",):
                spec = "*"
            try:
                entries = sorted(os.listdir(base), key=str.lower)
            except OSError:
                entries = []
            files_ = [e for e in entries if os.path.isfile(os.path.join(base, e))
                      and fnmatch.fnmatch(e.lower(), spec.lower())]
            dirs = [e for e in entries if os.path.isdir(os.path.join(base, e))]
            a = BArray(arr, [len(files_) + len(dirs) + 1, 4])
            interp.arrays[arr] = a
            a.set((0, 0), str(len(files_)))
            a.set((0, 1), str(len(dirs)))
            a.set((0, 2), base)
            for i, e in enumerate(files_, start=1):
                full = os.path.join(base, e)
                st_ = os.stat(full)
                a.set((i, 0), e)
                a.set((i, 1), str(st_.st_size))
                a.set((i, 2), time.strftime("%m/%d/%Y %H:%M:%S", time.localtime(st_.st_mtime)))
            for j, d in enumerate(dirs, start=len(files_) + 1):
                a.set((j, 1), d)
        self.emit(op, st.line)

    def c_sort(self, st):
        a, b = self.cexpr(st.start), self.cexpr(st.end)
        col = self.cexpr(st.col) if st.col else None
        name = st.array
        interp = self

        def op(fr):
            arr = interp.arrays.get(name)
            if arr is None:
                raise BasicError(f"SORT: array {name}() doesn't exist")
            lo, hi = int(a(fr)), int(b(fr))
            desc = lo > hi
            lo, hi = min(lo, hi), max(lo, hi)
            if len(arr.dims) == 1:
                hi = min(hi, arr.dims[0] - 1)
                seg = arr.data[lo:hi + 1]
                seg.sort(key=_sort_key, reverse=desc)
                arr.data[lo:hi + 1] = seg
            else:
                c = int(col(fr)) if col else 0
                w = arr.dims[1]
                hi = min(hi, arr.dims[0] - 1)
                rows = [arr.data[r * w:(r + 1) * w] for r in range(lo, hi + 1)]
                rows.sort(key=lambda row: _sort_key(row[c]), reverse=desc)
                for k, row in enumerate(rows):
                    r = lo + k
                    arr.data[r * w:(r + 1) * w] = row
        self.emit(op, st.line)

    def c_maphandle(self, st):
        old = self.chandle(st.old)
        new = self.chandle(st.new) if st.new[0] == "handle" else self.cexpr(st.new)
        interp = self

        def op(fr):
            o = old(fr)
            n = str(new(fr)).strip().lower()
            if not n.startswith("#"):
                n = "#" + n
            if o in interp.files:
                f = interp.files.pop(o)
                f.handle = n
                interp.files[n] = f
            else:
                interp.host.rename_handle(o, n)
        self.emit(op, st.line)

    # ---- files and windows ----
    def c_open(self, st):
        name = self.cexpr(st.name)
        h = self.chandle(st.handle)
        reclen = self.cexpr(st.reclen) if st.reclen else None
        mode = st.mode
        interp = self
        file_modes = ("input", "output", "append", "random", "binary")

        def op(fr):
            key = h(fr)
            if key in interp.files or interp.host.is_gui_handle(key):
                raise BasicError(f"Handle {key} is already open")
            n = to_str(name(fr))
            if mode in file_modes:
                path = interp.resolve(n, must_exist=(mode == "input"))
                interp.files[key] = BFile(key, path, mode, reclen(fr) if reclen else None)
            elif mode == "dll":
                interp.dll_handles[key] = n
            else:
                interp.host.open_window(key, n, mode, interp.window_settings())
        self.emit(op, st.line)

    def window_settings(self):
        g = self.gvars
        return {
            "width": int(_num(g["WindowWidth"], "WindowWidth")),
            "height": int(_num(g["WindowHeight"], "WindowHeight")),
            "x": int(_num(g["UpperLeftX"], "UpperLeftX")),
            "y": int(_num(g["UpperLeftY"], "UpperLeftY")),
            "bg": g.get("BackgroundColor$", ""),
            "fg": g.get("ForegroundColor$", ""),
            "textbox": g.get("TextboxColor$", ""),
            "listbox": g.get("ListboxColor$", ""),
            "combobox": g.get("ComboboxColor$", ""),
            "texteditor": g.get("TexteditorColor$", ""),
        }

    def c_close(self, st):
        hs = [self.chandle(x) for x in st.handles]
        interp = self

        def op(fr):
            for h in hs:
                key = h(fr)
                f = interp.files.pop(key, None)
                if f is not None:
                    f.close()
                elif key in interp.dll_handles:
                    interp.dll_handles.pop(key)
                elif interp.host.is_gui_handle(key):
                    interp.host.close_gui(key)
                else:
                    raise BasicError(f"Can't close {key}: it isn't open")
        self.emit(op, st.line)

    def file(self, key):
        f = self.files.get(key)
        if f is None:
            raise BasicError(f"File {key} is not open")
        return f

    def c_seek(self, st):
        h, p = self.chandle(st.handle), self.cexpr(st.pos)
        interp = self
        self.emit(lambda fr: interp.file(h(fr)).seek(p(fr)), st.line)

    def c_field(self, st):
        h = self.chandle(st.handle)
        fields = [(self.cexpr(w), self.clvalue(t), self.cexpr(t), t[1].endswith("$")) for w, t in st.fields]
        interp = self

        def op(fr):
            interp.file(h(fr)).fields = fields
        self.emit(op, st.line)

    def c_put(self, st):
        h, r = self.chandle(st.handle), self.cexpr(st.rec)
        interp = self

        def op(fr):
            f = interp.file(h(fr))
            vals = [(int(w(fr)), to_str(g(fr))) for w, s, g, is_str in f.fields]
            f.put(r(fr), vals)
        self.emit(op, st.line)

    def c_get(self, st):
        h, r = self.chandle(st.handle), self.cexpr(st.rec)
        trim = st.trim
        interp = self

        def op(fr):
            f = interp.file(h(fr))
            widths = [int(w(fr)) for w, s, g, is_str in f.fields]
            data = f.get(r(fr), widths)
            for (w, s, g, is_str), d in zip(f.fields, data):
                if trim:
                    d = d.strip()
                s(fr, d if is_str else val(d))
        self.emit(op, st.line)

    # ---- GUI declarations ----
    def c_control(self, st):
        args = []
        for a in st.args:
            if a[0] == "e":
                node = a[1]
                args.append(("e", node, self.cexpr(node) if node[0] != "call" or node[2] else None))
            else:
                args.append(a + (None,) if len(a) == 2 else a)
        h = self.chandle(st.handle)
        ctype = st.ctype
        interp = self
        line = st.line
        for a in st.args:
            if a[0] == "label":
                self.pending_labels.append((a[1], line))

        def op(fr):
            spec = interp.build_control(fr, ctype, h(fr), st.handle[1], args)
            if ctype == "menu":
                interp.host.declare_menu(spec)
            else:
                interp.host.declare_control(spec)
        self.emit(op, st.line)

    def build_control(self, fr, ctype, key, raw_handle, args):
        pos = 0

        def take(kind):
            nonlocal pos
            if pos >= len(args):
                return None
            a = args[pos]
            pos += 1
            return a

        def handler(a):
            if a is None:
                return None
            if a[0] == "label":
                return ("label", a[1])
            if a[0] == "e" and a[1][0] == "var":
                return ("sub", a[1][1])
            if a[0] == "e" and a[1][0] == "str" and a[1][1].startswith("["):
                return ("label", a[1][1].strip("[]").lower())
            raise BasicError("Expected a branch label like [myLabel] or a SUB name")

        def value(a):
            if a is None:
                return None
            if a[0] != "e":
                raise BasicError(f"Unexpected {a[0]} in {ctype} statement")
            if a[2] is None:
                raise BasicError(f"Unexpected array in {ctype} statement")
            return a[2](fr)

        def num(a, what):
            v = value(a)
            if v is None:
                return None
            if isinstance(v, str):
                raise BasicError(f"{ctype}: {what} should be a number")
            return int(v)

        def corner(a):
            if a is None:
                return "ul"
            if a[0] == "e" and a[1][0] == "var" and a[1][1].lower() in ("ul", "ur", "ll", "lr"):
                return a[1][1].lower()
            if a[0] == "e" and a[1][0] == "str":
                return a[1][1].lower()
            raise BasicError(f"{ctype}: expected UL, UR, LL or LR")

        spec = {"type": ctype, "handle": key, "raw": raw_handle}
        if ctype == "menu":
            title = value(take("e"))
            items = []
            while pos < len(args):
                a = take("e")
                if a[0] == "sep":
                    items.append(None)
                    continue
                text = value(a)
                hd = handler(take("h"))
                items.append((to_str(text), hd))
            spec.update(title=to_str(title), items=items)
            return spec
        if ctype in ("button", "bmpbutton"):
            text = to_str(value(take("e")))
            spec["handler"] = handler(take("h"))
            spec["corner"] = corner(take("c"))
            spec["x"] = num(take("e"), "x")
            spec["y"] = num(take("e"), "y")
            spec["w"] = num(take("e"), "width")
            spec["h"] = num(take("e"), "height")
            if ctype == "bmpbutton":
                real = self.resolve(text)
                if not os.path.exists(real):
                    raise BasicError(f"Bitmap file not found for bmpbutton: {text}")
                spec["file"] = real
                spec["text"] = ""
            else:
                spec["text"] = text
        elif ctype in ("textbox", "texteditor", "graphicbox"):
            spec["x"], spec["y"], spec["w"], spec["h"] = (num(take("e"), "x"), num(take("e"), "y"),
                                                          num(take("e"), "width"), num(take("e"), "height"))
        elif ctype in ("statictext", "groupbox"):
            spec["text"] = to_str(value(take("e")))
            spec["x"], spec["y"], spec["w"], spec["h"] = (num(take("e"), "x"), num(take("e"), "y"),
                                                          num(take("e"), "width"), num(take("e"), "height"))
        elif ctype in ("listbox", "combobox"):
            a = take("e")
            if a is None or a[0] != "e" or a[1][0] not in ("call", "var"):
                raise BasicError(f"{ctype}: expected an array like items$()")
            arrname = a[1][1]
            interp = self

            def items(arrname=arrname):
                arr = interp.arrays.get(arrname)
                if arr is None:
                    return []
                return [to_str(x) for x in arr.items_1d() if to_str(x) != ""]
            spec["items"] = items
            spec["array"] = arrname
            spec["handler"] = handler(take("h"))
            spec["x"], spec["y"], spec["w"], spec["h"] = (num(take("e"), "x"), num(take("e"), "y"),
                                                          num(take("e"), "width"), num(take("e"), "height"))
        elif ctype in ("checkbox", "radiobutton"):
            spec["text"] = to_str(value(take("e")))
            spec["set"] = handler(take("h"))
            spec["reset"] = handler(take("h"))
            spec["x"], spec["y"], spec["w"], spec["h"] = (num(take("e"), "x"), num(take("e"), "y"),
                                                          num(take("e"), "width"), num(take("e"), "height"))
        for k in ("x", "y"):
            if spec.get(k) is None:
                spec[k] = 0
        return spec

    def c_popupmenu(self, st):
        args = st.args
        compiled = [(a[0], a[1], self.cexpr(a[1]) if a[0] == "e" else None) for a in args]
        interp = self

        def op(fr):
            items = []
            i = 0
            while i < len(compiled):
                kind, node, f = compiled[i]
                if kind == "sep":
                    items.append(None)
                    i += 1
                    continue
                text = to_str(f(fr))
                hd = None
                if i + 1 < len(compiled):
                    k2, n2, _ = compiled[i + 1]
                    if k2 == "label":
                        hd = ("label", n2)
                    elif k2 == "e" and n2[0] == "var":
                        hd = ("sub", n2[1])
                items.append((text, hd))
                i += 2
            choice = interp.host.popupmenu(items)
            if choice is not None:
                return interp.dispatch(Event(choice, ["#popup"]), fr)
        self.emit(op, st.line)

    def c_calldll(self, st):
        h = self.chandle(st.handle)
        fn = self.cexpr(st.func)
        args = [(self.cexpr(e), t) for e, t in st.args]
        ret = st.ret
        ret_set = self.clvalue(ret[0]) if ret and ret[0][0] in ("var", "call") else None
        ret_type = ret[1] if ret else "void"
        interp = self

        def op(fr):
            from .dllemu import call_dll
            key = h(fr)
            lib = interp.dll_handles.get(key, key.lstrip("#"))
            r = call_dll(interp, lib, to_str(fn(fr)), [(a(fr), t) for a, t in args], ret_type)
            if ret_set:
                if ret[0][1].endswith("$"):
                    ret_set(fr, to_str(r))
                else:
                    ret_set(fr, r if not isinstance(r, str) else val(r))
        self.emit(op, st.line)

    # ------------------------------------------------------------- running
    def run(self):
        """Run the program until it ends. Raises BasicError on errors."""
        main = Frame(self.main, self.gvars)
        self.frames = [main]
        self.main_frame = main
        try:
            try:
                self.run_frame(main)
                # Fell off the end of the program. If windows are still open
                # keep handling their events instead of quitting.
                while self.host.has_windows():
                    main.pc = len(self.main.code)
                    target = self.do_wait(main)
                    main.pc = target
                    self.run_frame(main)
            except EndProgram:
                pass
        finally:
            self.ended = True
            for f in list(self.files.values()):
                try:
                    f.close()
                except Exception:
                    pass
            self.files.clear()

    def depth(self):
        return sum(1 + len(f.gosub) for f in self.frames)

    def run_frame(self, fr):
        code = fr.unit.code
        n = len(code)
        host = self.host
        dbg = self.debugger
        count = 0
        while True:
            try:
                return self._run_ops(fr, code, n, host, dbg, count)
            except BasicError as e:
                trap = self.error_label
                if trap is None or trap[0] is not fr.unit or trap[1] not in fr.unit.labels:
                    raise
                self.gvars["Err$"] = e.msg
                self.gvars["Err"] = 1
                fr.pc = fr.unit.labels[trap[1]]

    def _run_ops(self, fr, code, n, host, dbg, count):
        try:
            while True:
                pc = fr.pc
                if pc >= n:
                    return
                op = code[pc]
                if dbg is not None and op.first:
                    self.current_line = op.line
                    self._debug_check(fr, op)
                count += 1
                if count >= 500:
                    count = 0
                    self.current_line = op.line
                    host.pump()
                fr.pc = pc + 1
                r = op.fn(fr)
                if r is not None:
                    if r is RETURN:
                        return
                    fr.pc = r
        except BasicError as e:
            if e.line is None:
                e.line = code[min(fr.pc, n) - 1].line if fr.pc else (code[0].line if code else 0)
            raise
        except (EndProgram, StopRequested):
            raise
        except RecursionError:
            raise BasicError("Too many nested calls (runaway recursion?)", code[max(fr.pc - 1, 0)].line)
        except ZeroDivisionError:
            raise BasicError("Division by zero", code[max(fr.pc - 1, 0)].line)
        except OverflowError:
            raise BasicError("Number too large", code[max(fr.pc - 1, 0)].line)
        except KeyError as e:
            raise BasicError(f"Internal lookup failed: {e}", code[max(fr.pc - 1, 0)].line)

    def _debug_check(self, fr, op):
        d = self.debugger
        line = op.line
        mode = d.mode
        pause = False
        if d.pause_requested:
            d.pause_requested = False
            pause = True
        elif line in d.breakpoints:
            pause = True
        elif mode == "step":
            pause = True
        elif mode == "over":
            pause = self.depth() <= d.target_depth
        elif mode == "out":
            pause = self.depth() < d.target_depth
        elif mode == "animate":
            self.host.debug_animate(self, fr, line)
            return
        if pause:
            self.host.debug_pause(self, fr, line)

    # helpers for the debugger UI
    def snapshot_vars(self, fr=None):
        fr = fr or (self.frames[-1] if self.frames else None)
        local = {}
        if fr is not None and fr.unit.kind != "main":
            local = dict(fr.vars)
        glob = {k: v for k, v in self.gvars.items()}
        return glob, local

    def call_stack(self):
        out = []
        for f in self.frames:
            name = f.unit.name if f.unit.kind != "main" else "main program"
            out.append((name, len(f.gosub)))
        return out


# ---------------------------------------------------------------- helpers
def _num(v, what):
    if isinstance(v, str):
        raise BasicError(f"{what} must be a number, not a string")
    return v


def _check_nums(a, b, op):
    if isinstance(a, str) or isinstance(b, str):
        raise BasicError(f"Type mismatch: '{op}' needs numbers")


def _num_op(a, b, op, f):
    if isinstance(a, str) or isinstance(b, str):
        raise BasicError(f"Type mismatch: '{op}' needs numbers")
    r = f(a, b)
    return r


def _not(v):
    if isinstance(v, str):
        raise BasicError("NOT needs a number")
    # Logical NOT: Just BASIC's bitwise NOT made "not(1 = 1)" true, a classic gotcha.
    return -1 if v == 0 else 0


# Queries that old programs send without variable names, answering with INPUT #handle:
# command -> (fixed arguments before the variable names, number of variables, needs '!')
_QUERIES = {
    "contents?": (0, 1, False), "selection?": (0, 1, False), "selectindex?": (0, 1, False),
    "value?": (0, 1, False), "modified?": (0, 1, True), "origin?": (0, 2, True),
    "lines": (0, 1, True), "line": (1, 1, True), "posxy": (0, 2, False), "spritexy?": (1, 2, False),
    "spritevisible?": (1, 1, False), "spritescale?": (1, 1, False), "spriteorient?": (1, 1, False),
    "spritecollides": (1, 1, False), "segment": (0, 1, False),
}


def _add_reply_slots(text):
    t = text.strip()
    if ";" in t or not t:
        return text
    bang = t.startswith("!")
    words = (t[1:] if bang else t).split()
    if not words:
        return text
    q = _QUERIES.get(words[0].lower())
    if q is None or (q[2] and not bang):
        return text
    fixed, nvars, _ = q
    have = len(words) - 1 - fixed
    if have >= nvars or have < 0:
        return text
    return t + "".join(f" __reply{i}" for i in range(have, nvars))


def _sort_key(v):
    if isinstance(v, str):
        return (1, v.lower(), v)
    return (0, v, "")


from .builtins import BUILTINS  # noqa: E402  (circular import on purpose)

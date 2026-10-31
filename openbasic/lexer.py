"""Tokenizer for Just BASIC / Liberty BASIC source code."""
import re

from .errors import BasicSyntaxError


class Tok:
    __slots__ = ("k", "v", "line", "col")

    def __init__(self, k, v, line, col):
        self.k = k      # 'num', 'str', 'id', 'handle', 'label', 'op', 'nl', 'eof'
        self.v = v
        self.line = line
        self.col = col

    def is_id(self, *words):
        return self.k == "id" and self.v.lower() in words

    def is_op(self, *ops):
        return self.k == "op" and self.v in ops

    def __repr__(self):
        return f"Tok({self.k},{self.v!r},L{self.line})"


_ID = re.compile(r"[A-Za-z][A-Za-z0-9_.]*\$?")
_NUM = re.compile(r"(\d+\.?\d*|\.\d+)([eE][+-]?\d+)?")
_HANDLE = re.compile(r"#([A-Za-z][A-Za-z0-9_.]*\$(?:\.[A-Za-z0-9_.]+)?|[A-Za-z0-9][A-Za-z0-9_.]*)")
_WINCON = re.compile(r"_[A-Za-z][A-Za-z0-9_]*")
_LABEL = re.compile(r"\[([^\]\s\[]+)\]")
_HEX = re.compile(r"&[hH]([0-9A-Fa-f]+)")
_AMPWORD = re.compile(r"&[A-Za-z0-9_]+")
_TWO = ("<=", ">=", "<>", "=<", "=>", "><")
_ONE = "+-*/^=<>(),;:|?"


def tokenize(src):
    """Return a list of Tok. Newlines are kept as 'nl' tokens."""
    toks = []
    lines = src.replace("\r\n", "\n").replace("\r", "\n").split("\n")
    stmt_start = True  # True when the next token begins a statement (for REM)
    continued = False
    for ln, text in enumerate(lines, start=1):
        i = 0
        n = len(text)
        line_had_tokens = False
        while i < n:
            c = text[i]
            if c in " \t\f\v":
                i += 1
                continue
            if c == "'":
                break
            if c == '"':
                j = text.find('"', i + 1)
                if j < 0:
                    j = n  # unterminated string runs to end of line
                    toks.append(Tok("str", text[i + 1:j], ln, i))
                    i = n
                else:
                    toks.append(Tok("str", text[i + 1:j], ln, i))
                    i = j + 1
                stmt_start = False
                line_had_tokens = True
                continue
            if c == "_" and i + 1 < n and text[i + 1].isalpha():
                # Windows API constant such as _WS_VISIBLE
                from .wincon import value as wincon_value
                m = _WINCON.match(text, i)
                toks.append(Tok("num", wincon_value(m.group(0)), ln, i))
                i = m.end()
                stmt_start = False
                line_had_tokens = True
                continue
            if c == "_" and (text[i + 1:].strip() == "" or text[i + 1:].lstrip().startswith("'")):
                # line continuation
                continued = True
                i = n
                break
            if c == "[":
                m = _LABEL.match(text, i)
                if m:
                    toks.append(Tok("label", m.group(1), ln, i))
                    i = m.end()
                    stmt_start = True
                    line_had_tokens = True
                    continue
                raise BasicSyntaxError("Malformed branch label", ln)
            if c == "#":
                m = _HANDLE.match(text, i)
                if m:
                    toks.append(Tok("handle", "#" + m.group(1), ln, i))
                    i = m.end()
                    stmt_start = False
                    line_had_tokens = True
                    continue
                raise BasicSyntaxError("Malformed handle after '#'", ln)
            if c == "&" and i + 1 < n and text[i + 1].isalnum():
                # &Colors: unquoted menu text (or &HFF hex)
                m = _AMPWORD.match(text, i)
                if not _HEX.fullmatch(m.group(0)):
                    toks.append(Tok("str", m.group(0), ln, i))
                    i = m.end()
                    stmt_start = False
                    line_had_tokens = True
                    continue
            if c == "&":
                m = _HEX.match(text, i)
                if m:
                    toks.append(Tok("num", int(m.group(1), 16), ln, i))
                    i = m.end()
                    stmt_start = False
                    line_had_tokens = True
                    continue
            if c.isdigit() or (c == "." and i + 1 < n and text[i + 1].isdigit()):
                m = _NUM.match(text, i)
                s = m.group(0)
                if "." in s or "e" in s or "E" in s:
                    v = float(s)
                else:
                    v = int(s)
                toks.append(Tok("num", v, ln, i))
                i = m.end()
                stmt_start = False
                line_had_tokens = True
                continue
            if c.isalpha():
                m = _ID.match(text, i)
                word = m.group(0)
                if stmt_start and word.lower() == "rem":
                    i = n
                    break
                toks.append(Tok("id", word, ln, i))
                i += len(word)
                low = word.lower()
                stmt_start = low in ("then", "else")
                line_had_tokens = True
                continue
            two = text[i:i + 2]
            if two in _TWO:
                v = {"=<": "<=", "=>": ">=", "><": "<>"}.get(two, two)
                toks.append(Tok("op", v, ln, i))
                i += 2
                stmt_start = False
                line_had_tokens = True
                continue
            if c in _ONE:
                toks.append(Tok("op", c, ln, i))
                i += 1
                stmt_start = c == ":"
                line_had_tokens = True
                continue
            if c == "!" or c == "\\" or c == "~" or c == "`" or c == "@":
                # stray character outside a string: ignore it like the original IDE tolerates
                i += 1
                continue
            raise BasicSyntaxError(f"Unexpected character '{c}'", ln)
        if continued:
            continued = False
            continue
        if line_had_tokens or not toks or toks[-1].k != "nl":
            toks.append(Tok("nl", None, ln, n))
        stmt_start = True
    toks.append(Tok("eof", None, len(lines) + 1, 0))
    return toks

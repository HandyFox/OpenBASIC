"""Parser: turns tokens into a flat list of statements.

Block structures (IF..END IF, FOR..NEXT, SUB..END SUB, ...) are produced as
separate marker statements and matched up by the compiler. Single-line IFs
contain their nested statements directly.

Expression nodes are tuples:
    ('num', v) ('str', v) ('var', name) ('call', name, [args])
    ('un', op, e) ('bin', op, l, r) ('handle', name)
"""
from .errors import BasicSyntaxError
from .lexer import tokenize


class S:
    """A statement node."""

    def __init__(self, kind, line, **kw):
        self.kind = kind
        self.line = line
        self.__dict__.update(kw)

    def __repr__(self):
        d = {k: v for k, v in self.__dict__.items() if k not in ("kind", "line")}
        return f"S({self.kind}@{self.line} {d})"


CONTROL_WORDS = {
    "button", "bmpbutton", "textbox", "texteditor", "statictext", "groupbox",
    "listbox", "combobox", "checkbox", "radiobutton", "graphicbox", "menu",
}

COMPARE_OPS = ("=", "<>", "<", ">", "<=", ">=")


class Parser:
    def __init__(self, src):
        self.toks = tokenize(src)
        self.i = 0
        self.inline_if = 0  # depth of single-line IF parsing (ELSE ends a part)

    # ---------- token helpers ----------
    def peek(self, o=0):
        return self.toks[min(self.i + o, len(self.toks) - 1)]

    def next(self):
        t = self.toks[self.i]
        if self.i < len(self.toks) - 1:
            self.i += 1
        return t

    def err(self, msg, tok=None):
        tok = tok or self.peek()
        raise BasicSyntaxError(msg, tok.line)

    def expect_op(self, op):
        t = self.peek()
        if not t.is_op(op):
            self.err(f"Expected '{op}'")
        return self.next()

    def accept_op(self, op):
        if self.peek().is_op(op):
            self.next()
            return True
        return False

    def expect_id(self, *words):
        t = self.peek()
        if not t.is_id(*words):
            self.err(f"Expected {words[0].upper()}")
        return self.next()

    def accept_id(self, *words):
        if self.peek().is_id(*words):
            return self.next()
        return None

    def at_end(self):
        t = self.peek()
        if t.k in ("nl", "eof") or t.is_op(":"):
            return True
        if self.inline_if and t.is_id("else"):
            return True
        return False

    # ---------- program ----------
    def parse_program(self):
        stmts = []
        while self.peek().k != "eof":
            t = self.peek()
            if t.k == "nl":
                self.next()
                continue
            # old-style line number at the start of a line acts as a label
            if t.k == "num" and isinstance(t.v, int) and (self.i == 0 or self.toks[self.i - 1].k == "nl"):
                self.next()
                stmts.append(S("label", t.line, name=str(t.v)))
                continue
            line_start = self.i
            st = self.statement()
            if st is not None:
                stmts.append(st)
            if self.peek().is_op(":"):
                self.next()
                continue
            if st is not None and st.kind in ("label", "else"):
                continue  # statements may follow a label/ELSE on the same line
            t = self.peek()
            if t.k not in ("nl", "eof"):
                self.err(f"Unexpected '{t.v}' (did you forget a comma or quote?)")
        return stmts

    # ---------- statements ----------
    def statement(self):
        t = self.peek()
        line = t.line
        if t.k == "label":
            self.next()
            return S("label", line, name=t.v.lower())
        if t.k == "handle":
            return self.gui_print(line)
        if t.is_op("?"):
            self.next()
            return self.print_rest(line, "print")
        if t.k != "id":
            self.err(f"Unexpected '{t.v}' at start of statement")
        word = t.v.lower()
        fn = getattr(self, "st_" + word.replace("$", "_s"), None) if "." not in word else None
        if word in CONTROL_WORDS:
            self.next()
            return self.control_decl(word, line)
        if fn is not None and not self.looks_like_assignment():
            self.next()
            return fn(line)
        return self.assignment(line)

    def looks_like_assignment(self):
        # "name = 5" where name happens to be a keyword without arguments
        nt = self.peek(1)
        return nt.is_op("=") and self.peek().v.lower() not in ("if", "for", "while", "select", "case", "do", "loop", "print", "let", "global", "dim")

    def assignment(self, line, let=False):
        t = self.peek()
        if t.k != "id":
            self.err("Expected a variable name")
        target = self.lvalue()
        if not self.accept_op("="):
            if target[0] == "var" and self.at_end():
                self.err(f"Unknown statement '{t.v}'")
            self.err("Expected '='")
        e = self.expr()
        return S("assign", line, target=target, expr=e)

    def lvalue(self):
        t = self.next()
        if t.k != "id":
            self.err("Expected a variable name", t)
        if self.peek().is_op("("):
            self.next()
            args = []
            if not self.peek().is_op(")"):
                args.append(self.expr())
                while self.accept_op(","):
                    args.append(self.expr())
            self.expect_op(")")
            return ("call", t.v, args)
        return ("var", t.v)

    def st_let(self, line):
        return self.assignment(line)

    # --- printing ---
    def handle_ref(self):
        t = self.next()
        if t.k != "handle":
            self.err("Expected a #handle", t)
        return ("handle", t.v)

    def gui_print(self, line):
        h = self.handle_ref()
        self.accept_op(",")
        items = self.print_items()
        return S("print", line, handle=h, items=items)

    def st_print(self, line):
        return self.print_rest(line, "print")

    def st_lprint(self, line):
        return self.print_rest(line, "lprint")

    def print_rest(self, line, kind):
        handle = None
        if self.peek().k == "handle":
            handle = self.handle_ref()
            if not self.accept_op(",") and not self.at_end():
                pass
        items = self.print_items()
        return S(kind, line, handle=handle, items=items)

    def print_items(self):
        items = []
        while not self.at_end():
            t = self.peek()
            if t.is_op(";", ","):
                self.next()
                items.append(("sep", t.v))
                continue
            items.append(("e", self.expr()))
        return items

    # --- input ---
    def st_input(self, line):
        return self.input_rest(line, False)

    def st_line(self, line):
        self.expect_id("input")
        return self.input_rest(line, True)

    def input_rest(self, line, whole_line):
        handle = None
        prompt = None
        if self.peek().k == "handle":
            handle = self.handle_ref()
            self.accept_op(",")
        elif self.peek().k == "str" and self.peek(1).is_op(";", ","):
            prompt = self.next().v
            sep = self.next().v
            if sep == ",":
                prompt += "? " if False else ""
        elif self.peek().k in ("str",) or (self.peek().k == "id" and not self.peek(1).is_op(",", "(") and not self.peek(1).k in ("nl", "eof") and not self.peek(1).is_op(":")):
            # input expression; var  (expression prompt)
            e = self.expr()
            if self.accept_op(";") or self.accept_op(","):
                prompt = e
            else:
                self.err("Expected ';' after INPUT prompt")
        targets = [self.lvalue()]
        while self.accept_op(","):
            targets.append(self.lvalue())
        return S("input", line, handle=handle, prompt=prompt, targets=targets, whole_line=whole_line)

    # --- if ---
    def st_if(self, line):
        cond = self.expr()
        if self.accept_id("then"):
            pass
        elif self.peek().is_id("goto"):
            pass
        else:
            self.err("Expected THEN")
        if self.peek().k in ("nl", "eof"):
            return S("if", line, cond=cond)
        then_part = self.inline_stmts()
        else_part = []
        if self.accept_id("else"):
            else_part = self.inline_stmts()
        return S("if1", line, cond=cond, then=then_part, els=else_part)

    def inline_stmts(self):
        line = self.peek().line
        if self.peek().k == "label":
            t = self.next()
            return [S("goto", line, label=t.v.lower())]
        if self.peek().k == "num" and isinstance(self.peek().v, int):
            t = self.next()
            return [S("goto", line, label=str(t.v))]
        self.inline_if += 1
        try:
            out = []
            while True:
                if self.peek().k in ("nl", "eof") or self.peek().is_id("else"):
                    break
                st = self.statement()
                if st is not None:
                    out.append(st)
                if not self.accept_op(":"):
                    break
            return out
        finally:
            self.inline_if -= 1

    def st_elseif(self, line):
        cond = self.expr()
        self.accept_id("then")
        return S("elseif", line, cond=cond)

    def st_else(self, line):
        if self.peek().is_id("if"):
            self.next()
            return self.st_elseif(line)
        return S("else", line)

    def st_endif(self, line):
        return S("endif", line)

    def st_end(self, line):
        t = self.peek()
        if t.is_id("if"):
            self.next()
            return S("endif", line)
        if t.is_id("sub"):
            self.next()
            return S("endsub", line)
        if t.is_id("function"):
            self.next()
            return S("endfunction", line)
        if t.is_id("select"):
            self.next()
            return S("endselect", line)
        return S("end", line)

    def st_stop(self, line):
        return S("end", line)

    # --- loops ---
    def st_for(self, line):
        t = self.next()
        if t.k != "id":
            self.err("Expected a loop variable", t)
        self.expect_op("=")
        start = self.expr()
        self.expect_id("to")
        end = self.expr()
        step = None
        if self.accept_id("step"):
            step = self.expr()
        return S("for", line, var=t.v, start=start, end=end, step=step)

    def st_next(self, line):
        var = None
        if self.peek().k == "id" and not self.peek().is_id("else"):
            var = self.next().v
        return S("next", line, var=var)

    def st_while(self, line):
        return S("while", line, cond=self.expr())

    def st_wend(self, line):
        return S("wend", line)

    def st_do(self, line):
        kind = None
        cond = None
        if self.accept_id("while"):
            kind, cond = "while", self.expr()
        elif self.accept_id("until"):
            kind, cond = "until", self.expr()
        return S("do", line, cond_kind=kind, cond=cond)

    def st_loop(self, line):
        kind = None
        cond = None
        if self.accept_id("while"):
            kind, cond = "while", self.expr()
        elif self.accept_id("until"):
            kind, cond = "until", self.expr()
        return S("loop", line, cond_kind=kind, cond=cond)

    def st_exit(self, line):
        t = self.next()
        if t.k != "id":
            self.err("Expected FOR, WHILE, DO, SUB or FUNCTION after EXIT", t)
        return S("exit", line, what=t.v.lower())

    def st_select(self, line):
        self.accept_id("case")
        e = None
        if not self.at_end():
            e = self.expr()
        return S("select", line, expr=e)

    def st_case(self, line):
        if self.accept_id("else"):
            return S("caseelse", line)
        items = [self.case_item()]
        while self.accept_op(","):
            items.append(self.case_item())
        return S("case", line, items=items)

    def case_item(self):
        e = self.expr()
        if self.accept_id("to"):
            return ("range", e, self.expr())
        return ("val", e)

    # --- jumps ---
    def label_target(self):
        t = self.next()
        if t.k == "label":
            return t.v.lower()
        if t.k == "num":
            return str(t.v)
        if t.k == "id":
            return t.v.lower()
        self.err("Expected a branch label like [myLabel]", t)

    def st_goto(self, line):
        return S("goto", line, label=self.label_target())

    def st_gosub(self, line):
        return S("gosub", line, label=self.label_target())

    def st_return(self, line):
        return S("return", line)

    # --- subs and functions ---
    def params(self, parens):
        ps = []
        if parens and not self.accept_op("("):
            parens = False
        while True:
            if parens and self.peek().is_op(")"):
                break
            if self.at_end():
                break
            byref = bool(self.accept_id("byref"))
            t = self.next()
            if t.k != "id":
                self.err("Expected a parameter name", t)
            ps.append((t.v, byref))
            if not self.accept_op(","):
                break
        if parens:
            self.expect_op(")")
        return ps

    def st_sub(self, line):
        t = self.next()
        if t.k != "id":
            self.err("Expected a SUB name", t)
        return S("sub", line, name=t.v, params=self.params(parens=True))

    def st_function(self, line):
        t = self.next()
        if t.k != "id":
            self.err("Expected a FUNCTION name", t)
        return S("function", line, name=t.v, params=self.params(parens=True))

    def st_call(self, line):
        t = self.next()
        if t.k != "id":
            self.err("Expected a SUB name after CALL", t)
        args = []
        if self.peek().is_op("(") :
            # call foo(a, b)  -- parenthesised argument list
            save = self.i
            self.next()
            if self.peek().is_op(")"):
                self.next()
            else:
                args.append(self.expr())
                while self.accept_op(","):
                    args.append(self.expr())
                if not self.accept_op(")"):
                    self.i = save
                    args = []
                    args.append(self.arg_expr())
                    while self.accept_op(","):
                        args.append(self.arg_expr())
                elif not self.at_end():
                    # it was actually an expression like (a + b) * 2
                    self.i = save
                    args = [self.arg_expr()]
                    while self.accept_op(","):
                        args.append(self.arg_expr())
        elif not self.at_end():
            args.append(self.arg_expr())
            while self.accept_op(","):
                args.append(self.arg_expr())
        return S("call", line, name=t.v, args=args)

    def arg_expr(self):
        if self.peek().k == "handle":
            return self.handle_ref()
        return self.expr()

    # --- declarations ---
    def dim_list(self, kind, line):
        decls = []
        while True:
            t = self.next()
            if t.k != "id":
                self.err("Expected an array name", t)
            dims = []
            if self.accept_op("("):
                dims.append(self.expr())
                while self.accept_op(","):
                    dims.append(self.expr())
                self.expect_op(")")
            decls.append((t.v, dims))
            if not self.accept_op(","):
                break
        return S(kind, line, decls=decls)

    def st_dim(self, line):
        return self.dim_list("dim", line)

    def st_redim(self, line):
        return self.dim_list("redim", line)

    def st_global(self, line):
        names = []
        inits = []
        while True:
            t = self.next()
            if t.k != "id":
                self.err("Expected a variable name", t)
            names.append(t.v)
            if self.accept_op("="):
                inits.append((t.v, self.expr()))
            if not self.accept_op(","):
                break
        return S("global", line, names=names, inits=inits)

    def st_data(self, line):
        vals = []
        while not self.at_end():
            t = self.peek()
            if t.is_op(","):
                self.next()
                continue
            if t.is_op("-") and self.peek(1).k == "num":
                self.next()
                vals.append(-self.next().v)
            elif t.k in ("num", "str"):
                vals.append(self.next().v)
            else:
                # unquoted word(s) -> string up to the next comma
                words = []
                while not self.at_end() and not self.peek().is_op(","):
                    words.append(str(self.next().v))
                vals.append(" ".join(words))
        return S("data", line, values=vals)

    def st_read(self, line):
        targets = [self.lvalue()]
        while self.accept_op(","):
            targets.append(self.lvalue())
        return S("read", line, targets=targets)

    def st_restore(self, line):
        label = None
        if not self.at_end():
            label = self.label_target()
        return S("restore", line, label=label)

    # --- simple statements ---
    def _simple(kind):
        def f(self, line):
            return S(kind, line)
        return f

    st_wait = _simple("wait")
    st_scan = _simple("scan")
    st_cls = _simple("cls")
    st_nomainwin = _simple("nomainwin")
    st_beep = _simple("beep")
    st_stopmidi = _simple("stopmidi")

    def st_rem(self, line):
        while self.peek().k not in ("nl", "eof"):
            self.next()
        return None

    def exprs(self):
        out = []
        if self.at_end():
            return out
        out.append(self.arg_expr())
        while self.accept_op(","):
            out.append(self.arg_expr())
        return out

    def st_timer(self, line):
        ms = self.expr()
        handler = None
        if self.accept_op(","):
            handler = self.handler_ref()
        return S("timer", line, ms=ms, handler=handler)

    def handler_ref(self):
        t = self.next()
        if t.k == "label":
            return ("label", t.v.lower())
        if t.k == "id":
            return ("sub", t.v)
        self.err("Expected a branch label or SUB name", t)

    def st_notice(self, line):
        return S("notice", line, expr=self.expr())

    def st_confirm(self, line):
        e = self.expr()
        if not (self.accept_op(";") or self.accept_op(",")):
            self.err("Expected ';' and a variable after CONFIRM")
        return S("confirm", line, expr=e, target=self.lvalue())

    def st_prompt(self, line):
        e = self.expr()
        if not (self.accept_op(";") or self.accept_op(",")):
            self.err("Expected ';' and a variable after PROMPT")
        return S("prompt", line, expr=e, target=self.lvalue())

    def st_filedialog(self, line):
        title = self.expr()
        self.expect_op(",")
        tmpl = self.expr()
        self.expect_op(",")
        return S("filedialog", line, title=title, template=tmpl, target=self.lvalue())

    def st_colordialog(self, line):
        c = self.expr()
        self.expect_op(",")
        return S("colordialog", line, color=c, target=self.lvalue())

    def st_fontdialog(self, line):
        c = self.expr()
        self.expect_op(",")
        return S("fontdialog", line, font=c, target=self.lvalue())

    def st_run(self, line):
        cmd = self.expr()
        mode = None
        if self.accept_op(","):
            t = self.next()
            mode = str(t.v).lower()
        return S("run", line, cmd=cmd, mode=mode)

    def st_loadbmp(self, line):
        name = self.expr()
        self.expect_op(",")
        return S("loadbmp", line, name=name, path=self.expr())

    def st_unloadbmp(self, line):
        return S("unloadbmp", line, name=self.expr())

    def st_playwave(self, line):
        f = self.expr()
        mode = None
        if self.accept_op(","):
            if self.peek().k == "id" and self.peek().v.lower() in ("sync", "async", "loop"):
                mode = self.next().v.lower()
            else:
                mode = self.expr()
        return S("playwave", line, file=f, mode=mode)

    def st_playmidi(self, line):
        f = self.expr()
        times = ("num", 1)
        target = None
        if self.accept_op(","):
            times = self.expr()
            if self.accept_op(","):
                target = self.lvalue()
        return S("playmidi", line, file=f, times=times, target=target)

    def st_kill(self, line):
        return S("kill", line, file=self.expr())

    def st_name(self, line):
        a = self.expr()
        self.expect_id("as")
        return S("name", line, old=a, new=self.expr())

    def st_files(self, line):
        path = self.expr()
        self.expect_op(",")
        spec = self.expr()
        self.expect_op(",")
        arr = self.lvalue()
        return S("files", line, path=path, spec=spec, array=arr[1])

    def st_sort(self, line):
        arr = self.lvalue()
        self.expect_op(",")
        a = self.expr()
        self.expect_op(",")
        b = self.expr()
        col = None
        if self.accept_op(","):
            col = self.expr()
        return S("sort", line, array=arr[1], start=a, end=b, col=col)

    def st_locate(self, line):
        x = self.expr()
        self.expect_op(",")
        return S("locate", line, x=x, y=self.expr())

    def st_seek(self, line):
        h = self.handle_ref()
        self.expect_op(",")
        return S("seek", line, handle=h, pos=self.expr())

    def st_get(self, line):
        h = self.handle_ref()
        self.expect_op(",")
        return S("get", line, handle=h, rec=self.expr(), trim=False)

    def st_gettrim(self, line):
        h = self.handle_ref()
        self.expect_op(",")
        return S("get", line, handle=h, rec=self.expr(), trim=True)

    def st_put(self, line):
        h = self.handle_ref()
        self.expect_op(",")
        return S("put", line, handle=h, rec=self.expr())

    def st_field(self, line):
        h = self.handle_ref()
        fields = []
        while self.accept_op(","):
            n = self.expr()
            self.expect_id("as")
            fields.append((n, self.lvalue()))
        return S("field", line, handle=h, fields=fields)

    def st_trace(self, line):
        self.exprs()
        return None

    def st_cursor(self, line):
        while not self.at_end():
            self.next()
        return None

    def st_stylebits(self, line):
        while not self.at_end():
            self.next()
        return None

    def st_randomize(self, line):
        e = None if self.at_end() else self.expr()
        return S("randomize", line, expr=e)

    def st_maphandle(self, line):
        old = self.handle_ref()
        self.expect_op(",")
        new = self.handle_ref() if self.peek().k == "handle" else self.expr()
        return S("maphandle", line, old=old, new=new)

    def st_close(self, line):
        hs = [self.handle_ref()]
        while self.accept_op(","):
            hs.append(self.handle_ref())
        return S("close", line, handles=hs)

    def st_open(self, line):
        name = self.expr()
        self.expect_id("for")
        t = self.next()
        if t.k != "id":
            self.err("Expected a file or window type after FOR", t)
        mode = t.v.lower()
        self.expect_id("as")
        h = self.handle_ref()
        reclen = None
        if self.accept_id("len"):
            self.expect_op("=")
            reclen = self.expr()
        return S("open", line, name=name, mode=mode, handle=h, reclen=reclen)

    def st_calldll(self, line):
        h = self.handle_ref()
        self.expect_op(",")
        fn = self.expr()
        args = []
        while self.accept_op(","):
            e = self.expr()
            typ = "long"
            if self.accept_id("as"):
                typ = self.next().v.lower()
            args.append((e, typ))
        ret = None
        if args:
            last = args.pop()
            ret = last
        return S("calldll", line, handle=h, func=fn, args=args, ret=ret)

    def st_popupmenu(self, line):
        return S("popupmenu", line, args=self.generic_args())

    # --- GUI declarations ---
    def control_decl(self, word, line):
        h = self.handle_ref()
        self.accept_op(",")
        args = self.generic_args()
        return S("control", line, ctype=word, handle=h, args=args)

    def generic_args(self):
        args = []
        while not self.at_end():
            t = self.peek()
            if t.is_op(","):
                self.next()
                continue
            if t.k == "label":
                self.next()
                args.append(("label", t.v.lower()))
            elif t.is_op("|"):
                self.next()
                args.append(("sep",))
            else:
                args.append(("e", self.expr()))
        return args

    # ---------- expressions ----------
    def expr(self):
        return self.e_or()

    def e_or(self):
        l = self.e_and()
        while True:
            t = self.peek()
            if t.is_id("or", "xor"):
                self.next()
                l = ("bin", t.v.lower(), l, self.e_and())
            else:
                return l

    def e_and(self):
        l = self.e_not()
        while self.peek().is_id("and"):
            self.next()
            l = ("bin", "and", l, self.e_not())
        return l

    def e_not(self):
        if self.peek().is_id("not") and not self.peek(1).is_op("("):
            self.next()
            return ("un", "not", self.e_not())
        return self.e_cmp()

    def e_cmp(self):
        l = self.e_add()
        while True:
            t = self.peek()
            if t.k == "op" and t.v in COMPARE_OPS:
                self.next()
                l = ("bin", t.v, l, self.e_add())
            else:
                return l

    def e_add(self):
        l = self.e_mul()
        while True:
            t = self.peek()
            if t.is_op("+", "-"):
                self.next()
                l = ("bin", t.v, l, self.e_mul())
            else:
                return l

    def e_mul(self):
        l = self.e_unary()
        while True:
            t = self.peek()
            if t.is_op("*", "/"):
                self.next()
                l = ("bin", t.v, l, self.e_unary())
            elif t.is_id("mod"):
                self.next()
                l = ("bin", "mod", l, self.e_unary())
            else:
                return l

    def e_unary(self):
        t = self.peek()
        if t.is_op("-"):
            self.next()
            return ("un", "-", self.e_unary())
        if t.is_op("+"):
            self.next()
            return self.e_unary()
        return self.e_pow()

    def e_pow(self):
        l = self.atom()
        while self.peek().is_op("^"):
            self.next()
            r = self.e_pow_operand()
            l = ("bin", "^", l, r)
        return l

    def e_pow_operand(self):
        t = self.peek()
        if t.is_op("-"):
            self.next()
            return ("un", "-", self.e_pow_operand())
        return self.atom()

    def atom(self):
        t = self.next()
        if t.k == "num":
            return ("num", t.v)
        if t.k == "str":
            return ("str", t.v)
        if t.k == "handle":
            return ("handle", t.v)
        if t.is_op("("):
            e = self.expr()
            self.expect_op(")")
            return e
        if t.k == "id":
            if self.peek().is_op("("):
                self.next()
                args = []
                if not self.peek().is_op(")"):
                    args.append(self.arg_expr())
                    while self.accept_op(","):
                        args.append(self.arg_expr())
                self.expect_op(")")
                return ("call", t.v, args)
            return ("var", t.v)
        if t.k in ("nl", "eof"):
            self.err("Expression is incomplete", t)
        self.err(f"Unexpected '{t.v}' in expression", t)


def parse(src):
    return Parser(src).parse_program()

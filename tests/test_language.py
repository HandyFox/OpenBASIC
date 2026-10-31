"""Language tests that run without a display."""
import os
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from openbasic.errors import BasicError, BasicSyntaxError  # noqa: E402
from openbasic.host_base import TestHost  # noqa: E402
from openbasic.interp import Event, Interpreter  # noqa: E402
from openbasic import paths  # noqa: E402


def run(src, inputs=(), filename=None, events=()):
    h = TestHost(inputs)
    h.events = list(events)
    i = Interpreter(src, h, filename)
    i.run()
    return h.output(), h, i


def out(src, **kw):
    return run(src, **kw)[0]


def test_print_and_separators():
    assert out('print "a"; "b"; 3') == "ab3\n"
    assert out('print "x";\nprint "y"') == "xy\n"
    assert out('print 1, 2') == "1             2\n"
    assert out('print "a"; tab(5); "b"') == "a   b\n"


def test_numbers_format_like_just_basic():
    assert out("print 10/4; \" \"; 6/2; \" \"; 1/3") == "2.5 3 0.33333333\n"
    assert out("print 2^10, -2^2, 7 mod 3") == "1024          -4            1\n"
    assert out("print int(-2.5); \" \"; int(2.9)") == "-2 2\n"


def test_strings():
    src = '''
a$ = "Hello, World"
print len(a$); left$(a$, 5); right$(a$, 5); mid$(a$, 8, 3)
print instr(a$, "o"); " "; instr(a$, "o", 6); " "; upper$("abc"); lower$("DEF")
print "["; trim$("  x  "); "]"; word$("one two  three", 3); asc("A"); chr$(66)
print val("12.5abc") + 1; str$(7) + "!"
print using("####.##", 3.14159)
'''
    assert out(src) == ("12HelloWorldWor\n"
                        "5 9 ABCdef\n"
                        "[x]three65B\n"
                        "13.57!\n"
                        "   3.14\n")


def test_type_mismatch_is_reported_with_line():
    with pytest.raises(BasicError) as e:
        out('a = 1\nb$ = "x" + a')
    assert e.value.line == 2
    assert "Type mismatch" in e.value.msg


def test_if_forms():
    src = '''
x = 5
if x > 3 then print "big" else print "small"
if x = 5 then
    print "five"
elseif x = 6 then
    print "six"
else
    print "other"
end if
if x < 3 then [skip]
print "not skipped"
[skip]
if not(x = 4) then print "not four"
'''
    assert out(src) == "big\nfive\nnot skipped\nnot four\n"


def test_loops():
    src = '''
for i = 10 to 1 step -3 : print i; " "; : next i
print
while k < 3 : k = k + 1 : wend : print k
do
  j = j + 2
loop until j >= 7
print j
do while m < 2 : m = m + 1 : loop : print m
for a = 1 to 10
  if a = 4 then exit for
next a
print a
'''
    assert out(src) == "10 7 4 1 \n3\n8\n2\n4\n"


def test_select_case():
    src = '''
for n = 1 to 5
select case n
  case 1, 2 : print "low";
  case 3 : print "three";
  case else : print "high";
end select
next n
print
s$ = "b"
select case s$
  case "a" : print "A"
  case "b" : print "B"
end select
'''
    assert out(src) == "lowlowthreehighhigh\nB\n"


def test_gosub_sub_function_byref_global():
    src = '''
global g
g = 2
gosub [twice]
print g
call addTo g, 5
print g
x = 1
call bump x
print x
print fact(6); " "; greet$("Bo")
end
[twice]
  g = g * 2
  return
sub addTo byref v, n
  v = v + n
end sub
sub bump byref v
  v = v + 100
end sub
function fact(n)
  if n <= 1 then fact = 1 else fact = n * fact(n - 1)
end function
function greet$(n$)
  greet$ = "Hi " + n$
end function
'''
    assert out(src) == "4\n9\n101\n720 Hi Bo\n"


def test_sub_locals_dont_leak():
    src = '''
x = 1
call change
print x
end
sub change
  x = 99
end sub
'''
    assert out(src) == "1\n"


def test_arrays_and_sort():
    src = '''
dim a$(5)
a$(1) = "pear" : a$(2) = "apple" : a$(3) = "fig"
sort a$(), 1, 3
print a$(1); a$(2); a$(3)
dim n(3, 3)
n(2, 1) = 7
print n(2, 1)
b(9) = 4
print b(9)
'''
    assert out(src) == "applefigpear\n7\n4\n"


def test_array_out_of_range():
    with pytest.raises(BasicError) as e:
        out("dim a(3)\na(4) = 1")
    assert "Subscript out of range" in e.value.msg


def test_data_read_restore():
    src = '''
read a, b$
print a; b$
restore
read c
print c
data 3, "three", -1
'''
    assert out(src) == "3three\n3\n"


def test_input():
    assert out('input "Name? "; n$\nprint "Hi "; n$', inputs=["Ann"]) == "Name? Ann\nHi Ann\n"
    assert out('input x\nprint x * 2', inputs=["21"]) == "?21\n42\n"


def test_files_roundtrip(tmp_path):
    prog = tmp_path / "p.bas"
    src = '''
open "data.txt" for output as #f
print #f, "alpha"
print #f, "beta,gamma"
close #f
open "DATA.TXT" for input as #f
line input #f, a$
input #f, b$
input #f, c$
print a$; "|"; b$; "|"; c$; "|"; eof(#f)
close #f
open "data.txt" for append as #f
print #f, "delta"
close #f
open "data.txt" for input as #f
while eof(#f) = 0
  line input #f, l$
  n = n + 1
wend
close #f
print n
'''
    prog.write_text(src)
    assert out(src, filename=str(prog)) == "alpha|beta|gamma|-1\n3\n"


def test_random_access_file(tmp_path):
    prog = tmp_path / "r.bas"
    src = '''
open "recs.dat" for random as #r len = 20
field #r, 10 as name$, 10 as age$
name$ = "Ann" : age$ = "31"
put #r, 1
name$ = "Bob" : age$ = "42"
put #r, 2
gettrim #r, 1
print name$; age$
close #r
'''
    assert out(src, filename=str(prog)) == "Ann31\n"


def test_windows_paths_resolve(tmp_path):
    (tmp_path / "bmp").mkdir()
    (tmp_path / "bmp" / "CHECK.BMP").write_bytes(b"x")
    (tmp_path / "Barn.bmp").write_bytes(b"x")
    base = str(tmp_path)
    assert paths.resolve("bmp\\check.bmp", base, True) == str(tmp_path / "bmp" / "CHECK.BMP")
    assert paths.resolve("C:\\My Basic Files\\barn.BMP", base, True) == str(tmp_path / "Barn.bmp")
    assert paths.resolve("new.txt", base, False) == str(tmp_path / "new.txt")


def test_syntax_errors_name_the_line():
    with pytest.raises(BasicSyntaxError) as e:
        Interpreter("print 1\nfor i = 1 to 3\nprint i\n", TestHost())
    assert "FOR without NEXT" in e.value.msg
    with pytest.raises(BasicSyntaxError) as e:
        Interpreter("goto [nowhere]", TestHost())
    assert "[nowhere]" in e.value.msg


def test_wait_dispatches_events_and_return_after_wait():
    # A button handler reached while waiting inside a GOSUB can RETURN out of it,
    # which Ponderosa relies on.
    src = '''
gosub [dialog]
print "returned"
end
[dialog]
print "waiting"
wait
[ok]
print "ok pressed"
return
'''
    o, h, i = run(src, events=[Event(("label", "ok"))])
    assert o == "waiting\nok pressed\nreturned\n"


def test_sub_event_handler():
    src = '''
wait
sub clicked h$
  print "clicked "; h$
end sub
'''
    o, _, _ = run(src, events=[Event(("sub", "clicked"), ["#main.button1"])])
    assert o == "clicked #main.button1\n"


def test_eval_and_dates():
    assert out('x = 4\nprint eval("x * 2 + 1")') == "9\n"
    assert out('print date$("1/1/1901")') == "0\n"


def test_system_variables_case_insensitive():
    assert out("windowwidth = 500\nprint WindowWidth") == "500\n"


def test_user_samples_compile():
    here = os.path.join(os.path.dirname(__file__), "samples")
    for f in ("Ponderosa2.bas", "Target.bas"):
        src = open(os.path.join(here, f), encoding="utf-8", errors="replace").read()
        Interpreter(src, TestHost(), os.path.join(here, f))


def test_examples_compile():
    ex = os.path.join(os.path.dirname(os.path.dirname(__file__)), "openbasic", "examples")
    for f in os.listdir(ex):
        if f.endswith(".bas"):
            Interpreter(open(os.path.join(ex, f)).read(), TestHost(), os.path.join(ex, f))

"""Command line entry point.

    python -m openbasic                 open the IDE
    python -m openbasic file.bas        open file.bas in the IDE
    python -m openbasic --run file.bas  run a program without the IDE
"""
import os
import sys


def main(argv=None):
    argv = list(sys.argv[1:] if argv is None else argv)
    if argv and argv[0] in ("--run", "-r", "run"):
        if len(argv) < 2:
            print("usage: openbasic --run program.bas")
            return 2
        from .runtime.runner import main_standalone
        return main_standalone(os.path.abspath(argv[1]), argv=" ".join(argv[2:]))
    if argv and argv[0] in ("--version", "-V"):
        from . import __version__
        print("OpenBASIC", __version__)
        return 0
    # A standalone app made with "Make Standalone App" carries its program next to it
    from .standalone import find_bundled_program
    bundled = find_bundled_program()
    if bundled is not None:
        from .runtime.runner import main_standalone
        path, source = bundled
        return main_standalone(path, source=source, argv=" ".join(argv))
    from .ide.app import run_ide
    return run_ide(argv)


if __name__ == "__main__":
    sys.exit(main())

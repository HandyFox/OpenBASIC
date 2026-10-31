"""Exception types shared by the compiler, interpreter and runtimes."""


class BasicError(Exception):
    """A runtime error in a BASIC program."""

    def __init__(self, msg, line=None):
        super().__init__(msg)
        self.msg = msg
        self.line = line

    def __str__(self):
        if self.line:
            return f"Line {self.line}: {self.msg}"
        return self.msg


class BasicSyntaxError(BasicError):
    """A problem found while reading the program, before it runs."""


class EndProgram(Exception):
    """Raised to finish the program normally (END statement, last window closed...)."""


class StopRequested(Exception):
    """Raised when the user presses Stop in the IDE."""

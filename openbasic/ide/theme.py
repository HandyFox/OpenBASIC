"""Light and dark themes for the IDE (programs you run keep normal colors)."""
from PySide6.QtGui import QColor, QPalette
from PySide6.QtWidgets import QApplication, QStyleFactory

THEMES = {
    "light": {
        "window": "#f3f3f5", "base": "#ffffff", "alt": "#f6f6f8", "text": "#1f2328",
        "button": "#ececef", "highlight": "#2f6fdf", "hl_text": "#ffffff", "mid": "#c9c9cf",
        "gutter_bg": "#f3f3f5", "gutter_fg": "#8a8f98", "current_line": "#f2f6fd",
        "exec_line": "#fff3b0", "error_line": "#ffe0e0", "breakpoint": "#d73a49",
        "syn_keyword": "#0b4fbf", "syn_string": "#a3330f", "syn_comment": "#6a737d",
        "syn_number": "#116b2e", "syn_label": "#8a2be2", "syn_handle": "#b05a00",
        "syn_func": "#00639a", "syn_command": "#2a7a7a",
    },
    "dark": {
        "window": "#1f2126", "base": "#16181c", "alt": "#1c1e23", "text": "#d8dbe0",
        "button": "#2a2d33", "highlight": "#3d7bfd", "hl_text": "#ffffff", "mid": "#3a3e46",
        "gutter_bg": "#1b1d21", "gutter_fg": "#6b717c", "current_line": "#20242b",
        "exec_line": "#4a4320", "error_line": "#4a2326", "breakpoint": "#f0525f",
        "syn_keyword": "#6ea8ff", "syn_string": "#e6a26b", "syn_comment": "#7d8590",
        "syn_number": "#7fd18b", "syn_label": "#c792ea", "syn_handle": "#f0b45b",
        "syn_func": "#62c6e8", "syn_command": "#7fcfcf",
    },
}

current = dict(THEMES["light"])
current_name = "light"


def apply(name, app=None):
    global current, current_name
    current_name = name if name in THEMES else "light"
    current = dict(THEMES[current_name])
    app = app or QApplication.instance()
    app.setStyle(QStyleFactory.create("Fusion"))
    t = current
    pal = QPalette()
    pal.setColor(QPalette.Window, QColor(t["window"]))
    pal.setColor(QPalette.WindowText, QColor(t["text"]))
    pal.setColor(QPalette.Base, QColor(t["base"]))
    pal.setColor(QPalette.AlternateBase, QColor(t["alt"]))
    pal.setColor(QPalette.Text, QColor(t["text"]))
    pal.setColor(QPalette.Button, QColor(t["button"]))
    pal.setColor(QPalette.ButtonText, QColor(t["text"]))
    pal.setColor(QPalette.Highlight, QColor(t["highlight"]))
    pal.setColor(QPalette.HighlightedText, QColor(t["hl_text"]))
    pal.setColor(QPalette.ToolTipBase, QColor(t["base"]))
    pal.setColor(QPalette.ToolTipText, QColor(t["text"]))
    pal.setColor(QPalette.PlaceholderText, QColor(t["gutter_fg"]))
    pal.setColor(QPalette.Mid, QColor(t["mid"]))
    dis = QColor(t["gutter_fg"])
    for role in (QPalette.WindowText, QPalette.Text, QPalette.ButtonText):
        pal.setColor(QPalette.Disabled, role, dis)
    app.setPalette(pal)
    return current


from ..runtime.style import program_palette  # noqa: E402,F401

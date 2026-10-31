"""Colors and fonts the way Just BASIC names them."""
from PySide6.QtGui import QColor, QFont, QFontDatabase, QFontMetrics, QPalette

from ..errors import BasicError

NAMED_COLORS = {
    "white": (255, 255, 255),
    "black": (0, 0, 0),
    "lightgray": (192, 192, 192),
    "palegray": (192, 192, 192),
    "darkgray": (128, 128, 128),
    "red": (255, 0, 0),
    "darkred": (128, 0, 0),
    "pink": (255, 0, 255),
    "darkpink": (128, 0, 128),
    "blue": (0, 0, 255),
    "darkblue": (0, 0, 128),
    "green": (0, 255, 0),
    "darkgreen": (0, 128, 0),
    "cyan": (0, 255, 255),
    "darkcyan": (0, 128, 128),
    "yellow": (255, 255, 0),
    "brown": (128, 128, 0),
    "buttonface": (240, 240, 240),
}


def parse_color(spec, default=None):
    """'red', 'darkblue', '255 128 0', '#ff8000' -> QColor."""
    s = (spec or "").strip().lower()
    if not s:
        if default is not None:
            return QColor(default)
        raise BasicError("Missing color")
    if s in NAMED_COLORS:
        return QColor(*NAMED_COLORS[s])
    parts = s.replace(",", " ").split()
    if len(parts) == 3 and all(p.lstrip("-").replace(".", "", 1).isdigit() for p in parts):
        r, g, b = (max(0, min(255, int(float(p)))) for p in parts)
        return QColor(r, g, b)
    if s.startswith("#") and len(s) in (4, 7):
        c = QColor(s)
        if c.isValid():
            return c
    c = QColor(s)
    if c.isValid():
        return c
    raise BasicError(f"Unknown color '{spec}'. Use a name like red or three numbers like 255 128 0")


# Windows font names -> families likely to exist on any computer, narrowest first.
FAMILY_FALLBACKS = {
    "ms sans serif": ["Microsoft Sans Serif", "Segoe UI", "Tahoma", "Arial", "Helvetica", "Liberation Sans",
                      "FreeSans", "Carlito", "DejaVu Sans"],
    "microsoft sans serif": ["Microsoft Sans Serif", "Segoe UI", "Tahoma", "Arial", "Helvetica",
                             "Liberation Sans", "FreeSans", "DejaVu Sans"],
    "arial": ["Arial", "Helvetica", "Liberation Sans", "FreeSans", "DejaVu Sans"],
    "helvetica": ["Helvetica", "Arial", "Liberation Sans", "FreeSans"],
    "tahoma": ["Tahoma", "Verdana", "Arial", "Liberation Sans", "FreeSans", "DejaVu Sans"],
    "verdana": ["Verdana", "Tahoma", "DejaVu Sans"],
    "courier": ["Courier New", "Courier", "Liberation Mono", "FreeMono", "DejaVu Sans Mono", "Menlo", "Consolas"],
    "courier new": ["Courier New", "Courier", "Liberation Mono", "FreeMono", "DejaVu Sans Mono", "Menlo"],
    "fixedsys": ["Consolas", "Menlo", "DejaVu Sans Mono", "Courier New", "FreeMono"],
    "lucida console": ["Lucida Console", "Consolas", "Menlo", "DejaVu Sans Mono"],
    "times new roman": ["Times New Roman", "Times", "Liberation Serif", "FreeSerif", "DejaVu Serif"],
    "times": ["Times New Roman", "Times", "Liberation Serif", "FreeSerif", "DejaVu Serif"],
    "comic sans ms": ["Comic Sans MS", "Comic Neue", "Chalkboard", "DejaVu Sans"],
    "georgia": ["Georgia", "Times New Roman", "FreeSerif", "DejaVu Serif"],
    "segoe ui": ["Segoe UI", "Helvetica Neue", "Arial", "Inter", "DejaVu Sans"],
}
DEFAULT_FAMILY = "ms sans serif"
_available = None


def _families():
    global _available
    if _available is None:
        _available = {f.lower(): f for f in QFontDatabase.families()}
    return _available


def pick_family(name):
    name = name.replace("_", " ").strip().lower()
    avail = _families()
    if name in avail and name not in ("ms sans serif",):
        return avail[name]
    for cand in FAMILY_FALLBACKS.get(name, []) + FAMILY_FALLBACKS[DEFAULT_FAMILY]:
        if cand.lower() in avail:
            return avail[cand.lower()]
    return QFont().family()


def default_font():
    f = QFont(pick_family(DEFAULT_FAMILY))
    f.setPixelSize(12)
    return f


def parse_font(spec):
    """'ms_sans_serif 0 16', 'arial 12 bold', 'courier_new 8 12 italic' -> QFont.

    One number is a point size; two numbers are width and height in pixels.
    """
    words = spec.split()
    if not words:
        raise BasicError("FONT needs a font name")
    name_parts = []
    nums = []
    mods = []
    for w in words:
        lw = w.lower()
        try:
            nums.append(float(w))
            continue
        except ValueError:
            pass
        if nums or lw in ("bold", "italic", "underscore", "underline", "strikeout"):
            mods.append(lw)
        else:
            name_parts.append(w)
    f = QFont(pick_family(" ".join(name_parts)))
    if len(nums) >= 2:
        h = nums[1]
        if h <= 0:
            h = nums[0] * 2 if nums[0] > 0 else 16
        f.setPixelSize(max(6, int(round(h * 0.75))))
    elif len(nums) == 1 and nums[0] > 0:
        f.setPointSizeF(nums[0])
    else:
        f.setPixelSize(12)
    for m in mods:
        if m == "bold":
            f.setBold(True)
        elif m == "italic":
            f.setItalic(True)
        elif m in ("underscore", "underline"):
            f.setUnderline(True)
        elif m == "strikeout":
            f.setStrikeOut(True)
    return f


def css_color(c):
    return f"rgb({c.red()},{c.green()},{c.blue()})"


def program_palette():
    """Programs always run with a classic light look, whatever the IDE theme."""
    pal = QPalette()
    for role, c in ((QPalette.Window, "#f0f0f0"), (QPalette.WindowText, "#000000"),
                    (QPalette.Base, "#ffffff"), (QPalette.AlternateBase, "#f7f7f7"),
                    (QPalette.Text, "#000000"), (QPalette.Button, "#e9e9e9"),
                    (QPalette.ButtonText, "#000000"), (QPalette.Highlight, "#0a64d6"),
                    (QPalette.HighlightedText, "#ffffff"), (QPalette.ToolTipBase, "#ffffe1"),
                    (QPalette.ToolTipText, "#000000"), (QPalette.PlaceholderText, "#808080")):
        pal.setColor(role, QColor(c))
    pal.setColor(QPalette.Disabled, QPalette.ButtonText, QColor("#a0a0a0"))
    pal.setColor(QPalette.Disabled, QPalette.WindowText, QColor("#a0a0a0"))
    pal.setColor(QPalette.Disabled, QPalette.Text, QColor("#a0a0a0"))
    return pal

"""Toolbar icons drawn in code, so there are no image files to ship."""
from PySide6.QtCore import QPointF, QRectF, Qt
from PySide6.QtGui import QBrush, QColor, QFont, QIcon, QPainter, QPainterPath, QPen, QPixmap, QPolygonF

from . import theme

_cache = {}
S = 64


def clear_cache():
    _cache.clear()


def _fg():
    return QColor(theme.current["text"])


def _pm(draw):
    pm = QPixmap(S, S)
    pm.fill(Qt.transparent)
    p = QPainter(pm)
    p.setRenderHint(QPainter.Antialiasing)
    draw(p)
    p.end()
    return pm


def _pen(color, w=5):
    pen = QPen(QColor(color))
    pen.setWidthF(w)
    pen.setCapStyle(Qt.RoundCap)
    pen.setJoinStyle(Qt.RoundJoin)
    return pen


def _arrow(p, pts, color, head=True):
    p.setPen(_pen(color, 6))
    path = QPainterPath(QPointF(*pts[0]))
    for x, y in pts[1:]:
        path.lineTo(x, y)
    p.setBrush(Qt.NoBrush)
    p.drawPath(path)
    if head:
        (x1, y1), (x2, y2) = pts[-2], pts[-1]
        import math
        ang = math.atan2(y2 - y1, x2 - x1)
        a = 12
        p.drawLine(QPointF(x2, y2), QPointF(x2 - a * math.cos(ang - 0.6), y2 - a * math.sin(ang - 0.6)))
        p.drawLine(QPointF(x2, y2), QPointF(x2 - a * math.cos(ang + 0.6), y2 - a * math.sin(ang + 0.6)))


def _draw(name, p):
    fg = _fg()
    blue = QColor("#3b82f6")
    green = QColor("#22a559")
    red = QColor("#e5484d")
    amber = QColor("#f5a524")
    if name == "new":
        p.setPen(_pen(fg, 4))
        p.setBrush(Qt.NoBrush)
        path = QPainterPath()
        path.moveTo(16, 6); path.lineTo(40, 6); path.lineTo(50, 16); path.lineTo(50, 58); path.lineTo(16, 58); path.closeSubpath()
        p.drawPath(path)
        p.drawLine(40, 6, 40, 16); p.drawLine(40, 16, 50, 16)
    elif name == "open":
        p.setPen(_pen(fg, 4))
        p.setBrush(QColor(amber.red(), amber.green(), amber.blue(), 90))
        path = QPainterPath()
        path.moveTo(6, 14); path.lineTo(24, 14); path.lineTo(29, 20); path.lineTo(54, 20); path.lineTo(54, 52); path.lineTo(6, 52); path.closeSubpath()
        p.drawPath(path)
    elif name == "save":
        p.setPen(_pen(fg, 4))
        p.setBrush(Qt.NoBrush)
        p.drawRoundedRect(QRectF(8, 8, 48, 48), 5, 5)
        p.setBrush(QColor(blue))
        p.setPen(Qt.NoPen)
        p.drawRect(QRectF(18, 12, 24, 14))
        p.setPen(_pen(fg, 4))
        p.setBrush(Qt.NoBrush)
        p.drawRect(QRectF(16, 36, 32, 20))
    elif name == "run":
        p.setPen(Qt.NoPen)
        p.setBrush(green)
        p.drawPolygon(QPolygonF([QPointF(16, 8), QPointF(56, 32), QPointF(16, 56)]))
    elif name == "debug":
        p.setPen(Qt.NoPen)
        p.setBrush(green)
        p.drawPolygon(QPolygonF([QPointF(10, 8), QPointF(44, 28), QPointF(10, 48)]))
        p.setBrush(amber)
        p.drawEllipse(QPointF(46, 46), 13, 13)
        p.setPen(_pen("#ffffff", 4))
        p.drawLine(46, 39, 46, 47)
        p.drawPoint(46, 53)
    elif name == "stop":
        p.setPen(Qt.NoPen)
        p.setBrush(red)
        p.drawRoundedRect(QRectF(12, 12, 40, 40), 6, 6)
    elif name == "pause":
        p.setPen(Qt.NoPen)
        p.setBrush(blue)
        p.drawRoundedRect(QRectF(14, 10, 13, 44), 3, 3)
        p.drawRoundedRect(QRectF(37, 10, 13, 44), 3, 3)
    elif name == "step_into":
        _arrow(p, [(32, 6), (32, 40)], blue)
        p.setPen(Qt.NoPen); p.setBrush(fg); p.drawEllipse(QPointF(32, 54), 6, 6)
    elif name == "step_over":
        _arrow(p, [(10, 34), (14, 16), (32, 10), (50, 16), (54, 32)], blue)
        p.setPen(Qt.NoPen); p.setBrush(fg); p.drawEllipse(QPointF(32, 54), 6, 6)
    elif name == "step_out":
        _arrow(p, [(32, 44), (32, 8)], blue)
        p.setPen(Qt.NoPen); p.setBrush(fg); p.drawEllipse(QPointF(32, 56), 6, 6)
    elif name == "animate":
        p.setPen(Qt.NoPen)
        p.setBrush(green)
        p.drawPolygon(QPolygonF([QPointF(6, 12), QPointF(30, 32), QPointF(6, 52)]))
        p.drawPolygon(QPolygonF([QPointF(32, 12), QPointF(56, 32), QPointF(32, 52)]))
    elif name == "breakpoint":
        p.setPen(Qt.NoPen)
        p.setBrush(red)
        p.drawEllipse(QPointF(32, 32), 18, 18)
    elif name == "find":
        p.setPen(_pen(fg, 6))
        p.setBrush(Qt.NoBrush)
        p.drawEllipse(QPointF(27, 27), 16, 16)
        p.drawLine(39, 39, 56, 56)
    elif name == "check":
        p.setPen(_pen(green, 8))
        p.drawLine(10, 34, 26, 50)
        p.drawLine(26, 50, 54, 14)
    elif name == "designer":
        p.setPen(_pen(fg, 4))
        p.setBrush(Qt.NoBrush)
        p.drawRoundedRect(QRectF(6, 8, 52, 46), 4, 4)
        p.drawLine(6, 18, 58, 18)
        p.setPen(Qt.NoPen)
        p.setBrush(blue)
        p.drawRoundedRect(QRectF(14, 26, 22, 9), 2, 2)
        p.setBrush(QColor(blue.red(), blue.green(), blue.blue(), 120))
        p.drawRoundedRect(QRectF(14, 40, 36, 8), 2, 2)
    elif name == "package":
        p.setPen(_pen(fg, 4))
        p.setBrush(QColor(amber.red(), amber.green(), amber.blue(), 110))
        p.drawPolygon(QPolygonF([QPointF(32, 6), QPointF(56, 18), QPointF(56, 46), QPointF(32, 58),
                                 QPointF(8, 46), QPointF(8, 18)]))
        p.drawLine(8, 18, 32, 30); p.drawLine(56, 18, 32, 30); p.drawLine(32, 30, 32, 58)


def icon(name):
    key = (name, theme.current_name)
    ic = _cache.get(key)
    if ic is None:
        ic = QIcon(_pm(lambda p: _draw(name, p)))
        _cache[key] = ic
    return ic


def app_pixmap(size=256):
    pm = QPixmap(size, size)
    pm.fill(Qt.transparent)
    p = QPainter(pm)
    p.setRenderHint(QPainter.Antialiasing)
    s = size / 64.0
    p.scale(s, s)
    # a little retro monitor with a prompt
    p.setPen(Qt.NoPen)
    p.setBrush(QColor("#1d3b8f"))
    p.drawRoundedRect(QRectF(2, 4, 60, 46), 8, 8)
    p.setBrush(QColor("#0b1636"))
    p.drawRoundedRect(QRectF(7, 9, 50, 36), 4, 4)
    p.setBrush(QColor("#1d3b8f"))
    p.drawRect(QRectF(26, 50, 12, 6))
    p.drawRoundedRect(QRectF(16, 55, 32, 6), 3, 3)
    f = QFont("Courier New")
    f.setBold(True)
    f.setPixelSize(15)
    p.setFont(f)
    p.setPen(QColor("#7CFC9A"))
    p.drawText(QRectF(9, 11, 48, 32), Qt.AlignCenter, "BAS")
    p.setBrush(QColor("#7CFC9A"))
    p.setPen(Qt.NoPen)
    p.drawRect(QRectF(46, 36, 6, 3))
    p.end()
    return pm


def app_icon():
    ic = QIcon()
    for s in (16, 32, 48, 64, 128, 256):
        ic.addPixmap(app_pixmap(s))
    return ic

"""Graphics windows and graphicboxes: turtle drawing, bitmaps and sprites."""
import math

from PySide6.QtCore import QPointF, QRectF, Qt
from PySide6.QtGui import QColor, QFont, QFontMetrics, QImage, QPainter, QPen, QBrush, QPicture, QTransform
from PySide6.QtWidgets import QWidget

from ..errors import BasicError
from .style import parse_color, parse_font, pick_family

MOUSE_EVENTS = {
    "leftbuttondown", "leftbuttonup", "leftbuttonmove", "leftbuttondouble",
    "rightbuttondown", "rightbuttonup", "rightbuttonmove", "rightbuttondouble",
    "middlebuttondown", "middlebuttonup", "middlebuttonmove", "middlebuttondouble",
    "mousemove",
}
KEY_EVENTS = {"characterinput"}


def _is_bw(img, x0, y0, w, h):
    """True when a region only holds (near) black and white pixels."""
    if w <= 0 or h <= 0:
        return False
    step_x = max(1, w // 24)
    step_y = max(1, h // 24)
    for y in range(y0, y0 + h, step_y):
        for x in range(x0, x0 + w, step_x):
            c = img.pixel(x, y) & 0xFFFFFF
            r, g, b = (c >> 16) & 255, (c >> 8) & 255, c & 255
            if not ((r < 24 and g < 24 and b < 24) or (r > 232 and g > 232 and b > 232)):
                return False
    return True


def make_sprite_frame(img):
    """Convert a Just BASIC sprite bitmap (mask on top, picture below) to an image
    with transparency. Bitmaps without a mask are used as they are."""
    img = img.convertToFormat(QImage.Format_RGB32)
    w, h = img.width(), img.height()
    half = h // 2
    has_mask = h >= 2 and h % 2 == 0
    mask_top = True
    if has_mask:
        top_bw = _is_bw(img, 0, 0, w, half)
        bot_bw = _is_bw(img, 0, half, w, half)
        if top_bw:
            mask_top = True
        elif bot_bw:
            mask_top = False
        else:
            has_mask = False
    if not has_mask:
        return img.convertToFormat(QImage.Format_ARGB32)
    out = QImage(w, half, QImage.Format_ARGB32)
    my = 0 if mask_top else half
    py = half if mask_top else 0
    for y in range(half):
        for x in range(w):
            m = img.pixel(x, my + y) & 0xFFFFFF
            mr, mg, mb = (m >> 16) & 255, (m >> 8) & 255, m & 255
            alpha = 255 - (mr * 30 + mg * 59 + mb * 11) // 100
            p = img.pixel(x, py + y) & 0xFFFFFF
            out.setPixel(x, y, (alpha << 24) | p)
    return out


class Sprite:
    def __init__(self, name, frames):
        self.name = name
        self.frames = frames
        self.frame = 0
        self.x = 0.0
        self.y = 0.0
        self.visible = True
        self.scale = 100
        self.orient = "normal"
        self.offset = (0, 0)
        self.move = (0, 0)
        self.travel = None  # (tx, ty, speed, handler)
        self.cycle = 0
        self.cycle_once = False
        self._cache = {}

    def image(self):
        key = (self.frame, self.scale, self.orient)
        img = self._cache.get(key)
        if img is None:
            img = self.frames[self.frame % len(self.frames)]
            if self.orient == "mirror":
                img = img.mirrored(True, False)
            elif self.orient == "flip":
                img = img.mirrored(False, True)
            elif self.orient == "rotate180":
                img = img.mirrored(True, True)
            if self.scale != 100:
                w = max(1, int(img.width() * self.scale / 100))
                h = max(1, int(img.height() * self.scale / 100))
                img = img.scaled(w, h, Qt.IgnoreAspectRatio, Qt.FastTransformation)
            self._cache[key] = img
        return img

    def rect(self):
        img = self.image()
        return (int(self.x + self.offset[0]), int(self.y + self.offset[1]), img.width(), img.height())


class GraphicsView(QWidget):
    """A drawing surface. Used for graphicbox controls and graphics windows."""

    def __init__(self, host, key, parent=None, width=300, height=200):
        super().__init__(parent)
        self.host = host
        self.key = key
        self.setAttribute(Qt.WA_OpaquePaintEvent)
        self.setFocusPolicy(Qt.ClickFocus)
        self.setMouseTracking(True)
        self.img = QImage(max(1, width), max(1, height), QImage.Format_RGB32)
        self.img.fill(QColor(255, 255, 255))
        self.display = None
        self.sprite_mode = False
        self.background = None
        self.bg_offset = (0, 0)
        self.sprites = {}
        self.sprite_order = []
        self.handlers = {}
        self.pen = QColor(0, 0, 0)
        self.back = QColor(255, 255, 255)
        self.clear_color = QColor(255, 255, 255)
        self.size_ = 1
        self.down_ = True
        self.x = 0.0
        self.y = 0.0
        self.heading = 0.0  # degrees, 0 = north, clockwise
        self.font_ = QFont(pick_family("ms sans serif"))
        self.font_.setPixelSize(12)
        self.rule_xor = False
        self.segments = [[]]
        self.seg_base = 0
        self.base_img = None
        self.op_count = 0

    # ---------- painting ----------
    def ensure_size(self, w, h):
        if w <= self.img.width() and h <= self.img.height():
            return
        nw, nh = max(w, self.img.width()), max(h, self.img.height())
        new = QImage(nw, nh, QImage.Format_RGB32)
        new.fill(self.clear_color)
        p = QPainter(new)
        p.drawImage(0, 0, self.img)
        p.end()
        self.img = new

    def resizeEvent(self, ev):
        self.ensure_size(self.width(), self.height())
        super().resizeEvent(ev)

    def paintEvent(self, ev):
        p = QPainter(self)
        src = self.display if (self.sprite_mode and self.display is not None) else self.img
        p.fillRect(self.rect(), self.clear_color)
        p.drawImage(0, 0, src)
        p.end()

    def current_image(self):
        return self.display if (self.sprite_mode and self.display is not None) else self.img

    def painter(self):
        """A painter that records into the current segment; finish with _commit(p)."""
        pic = QPicture()
        p = QPainter(pic)
        p.setRenderHint(QPainter.Antialiasing, False)
        p._pic = pic
        return p

    def _commit(self, p):
        p.end()
        item = ("pic", p._pic, self.rule_xor)
        self._apply(item, self.img)
        self.segments[-1].append(item)
        self.op_count += 1
        if self.op_count > 200000:
            # keep memory bounded: older segments can no longer be deleted
            self.base_img = self.img.copy()
            self.segments = [[]]
            self.seg_base = self.segment_no()
            self.op_count = 0

    @staticmethod
    def _apply(item, img):
        if item[0] == "fill":
            img.fill(item[1])
            return
        ip = QPainter(img)
        if item[2]:
            ip.setCompositionMode(QPainter.RasterOp_SourceXorDestination)
        ip.drawPicture(0, 0, item[1])
        ip.end()

    def segment_no(self):
        return self.seg_base + len(self.segments)

    def redraw(self):
        if self.base_img is not None and self.base_img.size() == self.img.size():
            self.img = self.base_img.copy()
        else:
            self.img.fill(QColor(255, 255, 255))
            if self.base_img is not None:
                pt = QPainter(self.img)
                pt.drawImage(0, 0, self.base_img)
                pt.end()
        for seg in self.segments:
            for item in seg:
                self._apply(item, self.img)

    def _pen(self):
        pen = QPen(self.pen)
        pen.setWidth(max(1, int(self.size_)))
        return pen

    # ---------- events ----------
    def _fire(self, name, ev=None, key=None):
        handler = self.handlers.get(name)
        if not handler:
            return
        x = y = 0
        if ev is not None:
            pos = ev.position()
            x, y = int(pos.x()), int(pos.y())
        vars_ = {"MouseX": x, "MouseY": y}
        args = [self.key, x, y]
        if key is not None:
            vars_["Inkey$"] = key
            args = [self.key, key]
        self.host.push_event(handler, args, vars_, self.key, coalesce=(name.endswith("move")))

    @staticmethod
    def _btn(ev):
        b = ev.button()
        if b == Qt.LeftButton:
            return "left"
        if b == Qt.RightButton:
            return "right"
        if b == Qt.MiddleButton:
            return "middle"
        return None

    def mousePressEvent(self, ev):
        self.setFocus()
        b = self._btn(ev)
        if b:
            self._fire(b + "buttondown", ev)

    def mouseReleaseEvent(self, ev):
        b = self._btn(ev)
        if b:
            self._fire(b + "buttonup", ev)

    def mouseDoubleClickEvent(self, ev):
        b = self._btn(ev)
        if b:
            self._fire(b + "buttondouble", ev)

    def mouseMoveEvent(self, ev):
        btns = ev.buttons()
        if btns & Qt.LeftButton:
            self._fire("leftbuttonmove", ev)
        elif btns & Qt.RightButton:
            self._fire("rightbuttonmove", ev)
        elif btns & Qt.MiddleButton:
            self._fire("middlebuttonmove", ev)
        else:
            self._fire("mousemove", ev)

    def keyPressEvent(self, ev):
        from .keys import inkey_for
        k = inkey_for(ev)
        if k is not None:
            self.host.set_inkey(k)
            self._fire("characterinput", None, k)
        else:
            super().keyPressEvent(ev)

    # ---------- commands ----------
    def command(self, cmd, lookup):
        """Execute one or more ';' separated graphics commands. Returns query results."""
        result = {}
        text = cmd.strip()
        if not text:
            return result
        if text.startswith("\\") or text.startswith("|"):
            self._text(text[1:])
            self.update()
            return result
        for part in self._split(text):
            r = self._one(part.strip(), lookup)
            if r:
                result.update(r)
        self.update()
        return result

    @staticmethod
    def _split(text):
        parts = []
        cur = ""
        i = 0
        while i < len(text):
            c = text[i]
            if c == ";":
                parts.append(cur)
                cur = ""
                rest = text[i + 1:].lstrip()
                if rest.startswith("\\") or rest.startswith("|"):
                    parts.append(rest)
                    return parts
            else:
                cur += c
            i += 1
        parts.append(cur)
        return parts

    def _nums(self, words, count, cmd):
        try:
            vals = [float(w) for w in words[:count]]
        except ValueError:
            raise BasicError(f"Graphics command '{cmd}' needs {count} number(s)")
        if len(vals) < count:
            raise BasicError(f"Graphics command '{cmd}' needs {count} number(s)")
        return vals

    def _one(self, cmd, lookup):
        if not cmd:
            return None
        if cmd.startswith("\\") or cmd.startswith("|"):
            self._text(cmd[1:])
            return None
        words = cmd.split()
        op = words[0].lower()
        args = words[1:]
        n = lambda c: self._nums(args, c, op)
        if op == "cls":
            self.img.fill(QColor(255, 255, 255))
            self.segments = [[]]
            self.seg_base = 0
            self.base_img = None
            self.op_count = 0
            self.display = None
        elif op == "fill":
            c = parse_color(" ".join(args))
            self.clear_color = c
            item = ("fill", c)
            self._apply(item, self.img)
            self.segments[-1].append(item)
            self.display = None
        elif op == "color":
            self.pen = parse_color(" ".join(args))
        elif op == "backcolor":
            self.back = parse_color(" ".join(args))
        elif op == "size":
            self.size_ = max(1, n(1)[0])
        elif op in ("down", "pendown"):
            self.down_ = True
        elif op in ("up", "penup"):
            self.down_ = False
        elif op == "place":
            self.x, self.y = n(2)
        elif op == "goto":
            nx, ny = n(2)
            if self.down_:
                self._line(self.x, self.y, nx, ny)
            self.x, self.y = nx, ny
        elif op == "line":
            x1, y1, x2, y2 = n(4)
            self._line(x1, y1, x2, y2)
            self.x, self.y = x2, y2
        elif op in ("box", "boxfilled"):
            x2, y2 = n(2)
            p = self.painter()
            r = QRectF(min(self.x, x2), min(self.y, y2), abs(x2 - self.x), abs(y2 - self.y))
            if op == "boxfilled":
                p.fillRect(r, self.back)
            p.setPen(self._pen())
            p.setBrush(Qt.NoBrush)
            p.drawRect(r)
            self._commit(p)
        elif op in ("circle", "circlefilled"):
            r = n(1)[0]
            p = self.painter()
            p.setPen(self._pen())
            p.setBrush(QBrush(self.back) if op == "circlefilled" else Qt.NoBrush)
            p.drawEllipse(QPointF(self.x, self.y), r, r)
            self._commit(p)
        elif op in ("ellipse", "ellipsefilled"):
            w, h = n(2)
            p = self.painter()
            p.setPen(self._pen())
            p.setBrush(QBrush(self.back) if op == "ellipsefilled" else Qt.NoBrush)
            p.drawEllipse(QPointF(self.x, self.y), w / 2, h / 2)
            self._commit(p)
        elif op in ("pie", "piefilled"):
            w, h, a1, a2 = n(4)
            p = self.painter()
            p.setPen(self._pen())
            p.setBrush(QBrush(self.back) if op == "piefilled" else Qt.NoBrush)
            p.drawPie(QRectF(self.x - w / 2, self.y - h / 2, w, h), int(-a1 * 16), int(-a2 * 16))
            self._commit(p)
        elif op == "set":
            x, y = n(2)
            p = self.painter()
            if self.size_ <= 1:
                p.setPen(self.pen)
                p.drawPoint(QPointF(x, y))
            else:
                p.setPen(Qt.NoPen)
                p.setBrush(self.pen)
                p.drawEllipse(QPointF(x, y), self.size_ / 2, self.size_ / 2)
            self._commit(p)
            self.x, self.y = x, y
        elif op == "north":
            self.heading = 0.0
        elif op == "turn":
            self.heading = (self.heading + n(1)[0]) % 360
        elif op == "go":
            d = n(1)[0]
            rad = math.radians(self.heading)
            nx = self.x + d * math.sin(rad)
            ny = self.y - d * math.cos(rad)
            if self.down_:
                self._line(self.x, self.y, nx, ny)
            self.x, self.y = nx, ny
        elif op == "home":
            self.x = self.width() / 2
            self.y = self.height() / 2
        elif op == "posxy":
            out = {}
            if len(args) >= 1:
                out[args[0]] = _clean(self.x)
            if len(args) >= 2:
                out[args[1]] = _clean(self.y)
            return out
        elif op == "font":
            self.font_ = parse_font(" ".join(args))
        elif op == "flush":
            self.segments.append([])
        elif op == "discard":
            self.segments[-1] = []
            self.redraw()
        elif op == "redraw":
            self.redraw()
        elif op == "delsegment":
            k = int(self._nums(args, 1, op)[0]) - self.seg_base
            if 1 <= k <= len(self.segments):
                self.segments[k - 1] = []
                self.redraw()
        elif op in ("autoresize", "horizscrollbar", "vertscrollbar", "print", "stylebits", "trapclose",
                    "resizehandler"):
            pass
        elif op == "segment":
            return {args[0]: self.segment_no()} if args else None
        elif op == "rule":
            mode = (args[0].lower() if args else "over")
            self.rule_xor = mode == "xor"
        elif op == "when":
            if not args:
                raise BasicError("WHEN needs an event name like leftButtonDown")
            ev = args[0].lower()
            if ev not in MOUSE_EVENTS and ev not in KEY_EVENTS:
                raise BasicError(f"Unknown graphics event '{args[0]}'")
            if len(args) < 2:
                self.handlers.pop(ev, None)
            else:
                h = args[1]
                if h.startswith("["):
                    self.handlers[ev] = ("label", h.strip("[]").lower())
                else:
                    self.handlers[ev] = ("sub", h)
                if ev in KEY_EVENTS:
                    self.setFocusPolicy(Qt.StrongFocus)
        elif op == "setfocus":
            self.setFocusPolicy(Qt.StrongFocus)
            self.setFocus()
            self.window().activateWindow()
        elif op == "getbmp":
            if len(args) < 5:
                raise BasicError("getbmp needs a name, x, y, width and height")
            x, y, w, h = (int(float(v)) for v in args[1:5])
            self.host.bitmaps[args[0].lower()] = self.current_image().copy(x, y, w, h)
        elif op == "drawbmp":
            if len(args) < 3:
                raise BasicError("drawbmp needs a bitmap name, x and y")
            bmp = self.host.get_bitmap(args[0])
            x, y = float(args[1]), float(args[2])
            p = self.painter()
            p.drawImage(QPointF(x, y), bmp)
            self._commit(p)
        elif op == "bmpsave":
            if len(args) < 2:
                raise BasicError("bmpsave needs a bitmap name and a file name")
            bmp = self.host.get_bitmap(args[0])
            path = self.host.resolve_path(" ".join(args[1:]), must_exist=False)
            bmp.save(path, "BMP")
        elif op in ("enable", "disable", "show", "hide", "locate"):
            self.host.common_widget_cmd(self, op, args)
        # ---------- sprites ----------
        elif op == "background":
            if not args:
                raise BasicError("background needs a bitmap name")
            self.background = self.host.get_bitmap(args[0]).convertToFormat(QImage.Format_RGB32)
            self.sprite_mode = True
        elif op == "backgroundxy":
            x, y = n(2)
            self.bg_offset = (int(x), int(y))
        elif op == "addsprite":
            if len(args) < 2:
                raise BasicError("addsprite needs a sprite name and at least one bitmap name")
            frames = [self.host.get_sprite_frame(b) for b in args[1:]]
            s = Sprite(args[0].lower(), frames)
            old = self.sprites.get(s.name)
            if old:
                s.x, s.y = old.x, old.y
            else:
                self.sprite_order.append(s.name)
            self.sprites[s.name] = s
        elif op == "spriteimage":
            s = self._sprite(args, op)
            s.frames = [self.host.get_sprite_frame(b) for b in args[1:]]
            s.frame = 0
            s._cache.clear()
        elif op == "removesprite":
            name = args[0].lower() if args else ""
            if name in self.sprites:
                del self.sprites[name]
                self.sprite_order.remove(name)
        elif op == "spritexy":
            s = self._sprite(args, op)
            s.x, s.y = self._nums(args[1:], 2, op)
        elif op == "spritexy?":
            s = self._sprite(args, op)
            return {args[1]: _clean(s.x), args[2]: _clean(s.y)} if len(args) >= 3 else None
        elif op == "spritemovexy":
            s = self._sprite(args, op)
            s.move = tuple(self._nums(args[1:], 2, op))
        elif op == "spritetravelxy":
            s = self._sprite(args, op)
            tx, ty, speed = self._nums(args[1:], 3, op)
            handler = None
            if len(args) > 4:
                h = args[4]
                handler = ("label", h.strip("[]").lower()) if h.startswith("[") else ("sub", h)
            s.travel = (tx, ty, max(0.01, speed), handler)
            s.move = (0, 0)
        elif op == "spritevisible":
            s = self._sprite(args, op)
            s.visible = len(args) < 2 or args[1].lower() in ("on", "true", "1", "yes")
        elif op == "spritevisible?":
            s = self._sprite(args, op)
            return {args[1]: "true" if s.visible else "false"} if len(args) >= 2 else None
        elif op == "spritescale":
            s = self._sprite(args, op)
            s.scale = max(1, int(self._nums(args[1:], 1, op)[0]))
        elif op == "spritescale?":
            s = self._sprite(args, op)
            return {args[1]: s.scale} if len(args) >= 2 else None
        elif op == "spriteorient":
            s = self._sprite(args, op)
            s.orient = args[1].lower() if len(args) > 1 else "normal"
        elif op == "spriteorient?":
            s = self._sprite(args, op)
            return {args[1]: s.orient} if len(args) >= 2 else None
        elif op == "spriteoffset":
            s = self._sprite(args, op)
            x, y = self._nums(args[1:], 2, op)
            s.offset = (int(x), int(y))
        elif op == "centersprite":
            s = self._sprite(args, op)
            img = s.image()
            s.offset = (-img.width() // 2, -img.height() // 2)
        elif op == "cyclesprite":
            s = self._sprite(args, op)
            s.cycle = int(self._nums(args[1:], 1, op)[0])
            s.cycle_once = len(args) > 2 and args[2].lower() == "once"
        elif op == "spritetofront":
            s = self._sprite(args, op)
            self.sprite_order.remove(s.name)
            self.sprite_order.append(s.name)
        elif op == "spritetoback":
            s = self._sprite(args, op)
            self.sprite_order.remove(s.name)
            self.sprite_order.insert(0, s.name)
        elif op == "spriteround":
            pass
        elif op == "spritecollides":
            s = self._sprite(args, op)
            hits = self.collisions(s)
            if len(args) >= 2:
                return {args[1]: " ".join(hits)}
        elif op == "drawsprites":
            self.sprite_mode = True
            self.draw_sprites()
        else:
            raise BasicError(f"Unknown graphics command '{words[0]}'")
        return None

    def _sprite(self, args, op):
        if not args:
            raise BasicError(f"{op} needs a sprite name")
        s = self.sprites.get(args[0].lower())
        if s is None:
            raise BasicError(f"{op}: there is no sprite named '{args[0]}' (use addsprite first)")
        return s

    def _line(self, x1, y1, x2, y2):
        p = self.painter()
        p.setPen(self._pen())
        p.drawLine(QPointF(x1, y1), QPointF(x2, y2))
        self._commit(p)

    def _text(self, text):
        """Draw text at the pen. Every '\\' starts a new line, and the pen ends up
        one line below the text, so consecutive text commands stack."""
        p = self.painter()
        p.setPen(self.pen)
        p.setFont(self.font_)
        fm = QFontMetrics(self.font_)
        y = self.y
        for line in text.split("\\"):
            if line:
                p.drawText(QPointF(self.x, y), line)
            y += fm.height()
        self._commit(p)
        self.y = y

    # ---------- sprites ----------
    def draw_sprites(self):
        w, h = max(self.width(), 1), max(self.height(), 1)
        self.ensure_size(w, h)
        disp = QImage(self.img.size(), QImage.Format_RGB32)
        p = QPainter(disp)
        p.drawImage(0, 0, self.img)
        if self.background is not None:
            ox, oy = self.bg_offset
            p.drawImage(-ox, -oy, self.background)
        arrivals = []
        for name in list(self.sprite_order):
            s = self.sprites[name]
            # movement
            if s.travel:
                tx, ty, speed, handler = s.travel
                dx, dy = tx - s.x, ty - s.y
                dist = math.hypot(dx, dy)
                if dist <= speed:
                    s.x, s.y = tx, ty
                    s.travel = None
                    if handler:
                        arrivals.append(handler)
                else:
                    s.x += dx / dist * speed
                    s.y += dy / dist * speed
            elif s.move != (0, 0):
                s.x += s.move[0]
                s.y += s.move[1]
            if s.cycle and len(s.frames) > 1:
                nf = s.frame + s.cycle
                if s.cycle_once and (nf >= len(s.frames) or nf < 0):
                    s.cycle = 0
                else:
                    s.frame = nf % len(s.frames)
            if s.visible:
                x, y, _, _ = s.rect()
                p.drawImage(x, y, s.image())
        p.end()
        self.display = disp
        self.update()
        for h in arrivals:
            self.host.push_event(h, [self.key], {}, self.key)

    def collisions(self, s):
        if not s.visible:
            return []
        ax, ay, aw, ah = s.rect()
        hits = []
        for name in self.sprite_order:
            o = self.sprites[name]
            if o is s or not o.visible:
                continue
            bx, by, bw, bh = o.rect()
            x1, y1 = max(ax, bx), max(ay, by)
            x2, y2 = min(ax + aw, bx + bw), min(ay + ah, by + bh)
            if x1 >= x2 or y1 >= y2:
                continue
            ia, ib = s.image(), o.image()
            hit = False
            step = max(1, min(x2 - x1, y2 - y1) // 16)
            for yy in range(y1, y2, step):
                for xx in range(x1, x2, step):
                    if (ia.pixel(xx - ax, yy - ay) >> 24) > 64 and (ib.pixel(xx - bx, yy - by) >> 24) > 64:
                        hit = True
                        break
                if hit:
                    break
            if hit:
                hits.append(name)
        return hits


def _clean(v):
    return int(v) if float(v).is_integer() else round(v, 4)

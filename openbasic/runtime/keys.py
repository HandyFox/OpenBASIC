"""Keyboard helpers: Inkey$ values and Windows virtual-key codes."""
from PySide6.QtCore import QEvent, QObject, Qt

QT_TO_VK = {
    Qt.Key_Left: 37, Qt.Key_Up: 38, Qt.Key_Right: 39, Qt.Key_Down: 40,
    Qt.Key_Home: 36, Qt.Key_End: 35, Qt.Key_PageUp: 33, Qt.Key_PageDown: 34,
    Qt.Key_Insert: 45, Qt.Key_Delete: 46, Qt.Key_Shift: 16, Qt.Key_Control: 17,
    Qt.Key_Alt: 18, Qt.Key_Escape: 27, Qt.Key_Return: 13, Qt.Key_Enter: 13,
    Qt.Key_Tab: 9, Qt.Key_Backspace: 8, Qt.Key_Space: 32, Qt.Key_Pause: 19,
    Qt.Key_CapsLock: 20, Qt.Key_Meta: 91,
}
for _i in range(12):
    QT_TO_VK[getattr(Qt, f"Key_F{_i + 1}")] = 112 + _i

# keys that produce a two-character Inkey$ (chr$(0) + chr$(vk)) in Just BASIC
SPECIAL = {Qt.Key_Left, Qt.Key_Up, Qt.Key_Right, Qt.Key_Down, Qt.Key_Home, Qt.Key_End,
           Qt.Key_PageUp, Qt.Key_PageDown, Qt.Key_Insert, Qt.Key_Delete, Qt.Key_Shift,
           Qt.Key_Control, Qt.Key_Alt, Qt.Key_Pause, Qt.Key_CapsLock, Qt.Key_Meta}
SPECIAL |= {getattr(Qt, f"Key_F{i + 1}") for i in range(12)}


def vk_for(key):
    if key in QT_TO_VK:
        return QT_TO_VK[key]
    if Qt.Key_A <= key <= Qt.Key_Z:
        return 65 + (key - Qt.Key_A)
    if Qt.Key_0 <= key <= Qt.Key_9:
        return 48 + (key - Qt.Key_0)
    return None


def inkey_for(ev):
    key = ev.key()
    if key in SPECIAL:
        vk = vk_for(key)
        return chr(0) + chr(vk) if vk else None
    t = ev.text()
    if t:
        return t
    vk = vk_for(key)
    return chr(vk) if vk else None


class KeyTracker(QObject):
    """Application-wide key state, for GetAsyncKeyState emulation."""

    def __init__(self):
        super().__init__()
        self.down = set()

    def eventFilter(self, obj, ev):
        t = ev.type()
        if t in (QEvent.KeyPress, QEvent.KeyRelease) and not ev.isAutoRepeat():
            vk = vk_for(ev.key())
            if vk is not None:
                if t == QEvent.KeyPress:
                    self.down.add(vk)
                else:
                    self.down.discard(vk)
        elif t == QEvent.MouseButtonPress:
            b = ev.button()
            self.down.add({Qt.LeftButton: 1, Qt.RightButton: 2, Qt.MiddleButton: 4}.get(b, 0))
        elif t == QEvent.MouseButtonRelease:
            b = ev.button()
            self.down.discard({Qt.LeftButton: 1, Qt.RightButton: 2, Qt.MiddleButton: 4}.get(b, 0))
        elif t == QEvent.ApplicationDeactivate:
            self.down.clear()
        return False

    def state(self, vk):
        return -32767 if vk in self.down else 0

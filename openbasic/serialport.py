"""Serial ports: OPEN "COM1:9600,n,8,1" FOR RANDOM AS #comm.

Uses pyserial when it's installed (pip install pyserial). COMn maps to the
real port name on Windows; on macOS/Linux set OPENBASIC_COM1 (etc.) to a
device such as /dev/ttyUSB0, or the first USB serial device found is used.
"""
import glob
import os
import re
import sys

from .errors import BasicError


class SerialFile:
    def __init__(self, handle, port):
        self.handle = handle
        self.port = port
        self.mode = "serial"
        self.col = 0
        self.fields = []
        self.path = port.port

    def write(self, text):
        self.port.write(text.replace("\n", "\r").encode("latin-1", "replace"))

    def read_chars(self, n):
        return self.port.read(n).decode("latin-1")

    def read_line(self):
        return self.port.readline().decode("latin-1").rstrip("\r\n")

    read_item = read_line

    def lof(self):
        return self.port.in_waiting

    def loc(self):
        return 0

    def eof(self):
        return 0

    def seek(self, pos):
        pass

    def close(self):
        self.port.close()


def _device(n):
    env = os.environ.get(f"OPENBASIC_COM{n}")
    if env:
        return env
    if sys.platform.startswith("win"):
        return f"COM{n}"
    pats = ["/dev/tty.usbserial*", "/dev/tty.usbmodem*"] if sys.platform == "darwin" else \
        ["/dev/ttyUSB*", "/dev/ttyACM*", "/dev/ttyS*"]
    devs = sorted(d for p in pats for d in glob.glob(p))
    return devs[n - 1] if 0 < n <= len(devs) else None


def open_serial(handle, spec):
    m = re.match(r"^\s*COM(\d+):\s*(.*)$", spec, re.I)
    n = int(m.group(1))
    try:
        import serial
    except ImportError:
        raise BasicError(f"COM{n}: serial ports need the pyserial package (pip install pyserial)")
    dev = _device(n)
    if dev is None:
        raise BasicError(f"COM{n}: no serial port found (set OPENBASIC_COM{n} to the device name)")
    opts = [o.strip().lower() for o in m.group(2).split(",") if o.strip()]
    baud = int(opts[0]) if opts and opts[0].isdigit() else 9600
    parity = {"n": "N", "e": "E", "o": "O", "m": "M", "s": "S"}.get(opts[1][:1] if len(opts) > 1 else "n", "N")
    bits = int(opts[2]) if len(opts) > 2 and opts[2].isdigit() else 8
    stop = float(opts[3]) if len(opts) > 3 and opts[3].replace(".", "").isdigit() else 1
    try:
        port = serial.Serial(dev, baud, bytesize=bits, parity=parity, stopbits=stop, timeout=0.5)
    except Exception as e:
        raise BasicError(f"COM{n}: couldn't open {dev}: {e}")
    return SerialFile(handle, port)

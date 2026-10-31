"""Build the OpenBASIC IDE as a desktop app for this computer.

    pip install -r requirements.txt
    python build.py

Results land in dist/: OpenBASIC.exe (Windows), OpenBASIC.app (macOS) or
OpenBASIC (Linux). The same executable also serves as the runtime for
"Make Standalone App", so standalone builds are instant with it.
"""
import os
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
IS_WIN = sys.platform.startswith("win")
IS_MAC = sys.platform == "darwin"


def make_icons():
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    sys.path.insert(0, HERE)
    from PySide6.QtWidgets import QApplication
    app = QApplication.instance() or QApplication([])
    from openbasic.ide.icons import app_pixmap
    out = os.path.join(HERE, "build", "icons")
    os.makedirs(out, exist_ok=True)
    png = os.path.join(out, "openbasic.png")
    app_pixmap(512).save(png)
    try:
        from PIL import Image
        im = Image.open(png)
        im.save(os.path.join(out, "openbasic.ico"), sizes=[(16, 16), (32, 32), (48, 48), (64, 64), (128, 128), (256, 256)])
        im.save(os.path.join(out, "openbasic.icns"))
    except Exception as e:  # Pillow is optional
        print("icon conversion skipped:", e)
    return out


def main():
    icons = make_icons()
    sep = ";" if IS_WIN else ":"
    examples = os.path.join(HERE, "openbasic", "examples")
    args = [sys.executable, "-m", "PyInstaller", "--noconfirm", "--clean", "--windowed", "--name", "OpenBASIC",
            "--collect-submodules", "openbasic", "--paths", HERE,
            "--add-data", f"{examples}{sep}openbasic/examples"]
    from openbasic.ide.packager import EXCLUDES
    for m in EXCLUDES:
        args += ["--exclude-module", m]
    ico = os.path.join(icons, "openbasic.icns" if IS_MAC else "openbasic.ico")
    if os.path.exists(ico):
        args += ["--icon", ico]
    args += ["--onedir"] if IS_MAC else ["--onefile"]
    launcher = os.path.join(HERE, "build", "openbasic_launcher.py")
    with open(launcher, "w") as f:
        f.write("import sys\nfrom openbasic.__main__ import main\nsys.exit(main())\n")
    args.append(launcher)
    print(" ".join(args))
    subprocess.check_call(args, cwd=HERE)
    print("\nDone. Look in", os.path.join(HERE, "dist"))


if __name__ == "__main__":
    main()

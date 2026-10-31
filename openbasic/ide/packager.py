"""Make Standalone App: package a program so it runs without the IDE."""
import os
import re
import shutil
import sys
import tempfile

from PySide6.QtCore import QProcess, Qt
from PySide6.QtWidgets import (QCheckBox, QDialog, QDialogButtonBox, QFileDialog, QFormLayout, QHBoxLayout,
                               QLabel, QLineEdit, QListWidget, QListWidgetItem, QPlainTextEdit, QPushButton,
                               QVBoxLayout)

from .. import __version__, paths
from ..standalone import pack

IS_WIN = sys.platform.startswith("win")
IS_MAC = sys.platform == "darwin"
PLATFORM_NAME = "Windows" if IS_WIN else ("macOS" if IS_MAC else "Linux")
EXCLUDES = ["PySide6.QtWebEngineCore", "PySide6.QtWebEngineWidgets", "PySide6.QtWebEngineQuick",
            "PySide6.Qt3DCore", "PySide6.Qt3DRender", "PySide6.QtQuick", "PySide6.QtQml",
            "PySide6.QtCharts", "PySide6.QtDataVisualization", "PySide6.QtPdf", "PySide6.QtPdfWidgets",
            "PySide6.QtBluetooth", "PySide6.QtNfc", "PySide6.QtPositioning", "PySide6.QtLocation",
            "PySide6.QtSql", "PySide6.QtTest", "PySide6.QtDesigner", "tkinter", "numpy"]


def runtime_cache_dir():
    base = os.path.join(os.path.expanduser("~"), ".openbasic", "runtime",
                        f"{sys.platform}-{__version__}")
    os.makedirs(base, exist_ok=True)
    return base


def find_runtime():
    """Path of a runtime executable (or .app on macOS), or None if it must be built."""
    if getattr(sys, "frozen", False):
        exe = sys.executable
        if IS_MAC and "/Contents/MacOS/" in exe:
            return exe.split("/Contents/MacOS/")[0]
        return exe
    d = runtime_cache_dir()
    for cand in ("OpenBASICRuntime.app", "OpenBASICRuntime.exe", "OpenBASICRuntime"):
        p = os.path.join(d, cand)
        if os.path.exists(p) and (cand.endswith(".app") or os.path.isfile(p)):
            if IS_MAC and not cand.endswith(".app"):
                continue
            return p
    return None


def pyinstaller_command():
    """Command line that builds the runtime once into the cache."""
    pkg_parent = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    work = tempfile.mkdtemp(prefix="openbasic-build-")
    launcher = os.path.join(work, "obrun.py")
    with open(launcher, "w") as f:
        f.write("import sys\nfrom openbasic.__main__ import main\nsys.exit(main())\n")
    args = ["-m", "PyInstaller", "--noconfirm", "--clean", "--windowed", "--name", "OpenBASICRuntime",
            "--distpath", runtime_cache_dir(), "--workpath", os.path.join(work, "build"),
            "--specpath", work, "--paths", pkg_parent, "--collect-submodules", "openbasic"]
    args += ["--onedir"] if IS_MAC else ["--onefile"]
    for m in EXCLUDES:
        args += ["--exclude-module", m]
    args.append(launcher)
    return sys.executable, args, work


def referenced_files(source, base_dir):
    """Files in the program's folder that the program mentions in string literals."""
    found = []
    seen = set()
    for lit in re.findall(r'"([^"\n]*)"', source):
        candidates = [lit] + re.split(r"[\s,;]+", lit)
        for c in candidates:
            c = c.strip()
            if not c or len(c) > 260 or c.startswith(("!", "#")):
                continue
            if not re.search(r"\.[A-Za-z0-9]{1,5}$", c):
                continue
            real = paths.resolve(c, base_dir, must_exist=True)
            if real and os.path.isfile(real):
                try:
                    rel = os.path.relpath(real, base_dir)
                except ValueError:
                    continue
                if rel.startswith(".."):
                    # e.g. C:\My Basic Files\Barn.bmp that resolved into the program folder by name
                    continue
                if rel not in seen:
                    seen.add(rel)
                    found.append(rel)
    return found


class PackagerDialog(QDialog):
    def __init__(self, main, program_path):
        super().__init__(main)
        self.main = main
        self.program = program_path
        self.base_dir = os.path.dirname(program_path)
        self.stem = os.path.splitext(os.path.basename(program_path))[0]
        self.proc = None
        self.setWindowTitle("Make Standalone App")
        self.resize(640, 560)
        lay = QVBoxLayout(self)
        intro = QLabel(f"Packages <b>{os.path.basename(program_path)}</b> as an app for <b>{PLATFORM_NAME}</b> "
                       "that runs without OpenBASIC installed. To make apps for other systems, run this on "
                       "that system (or use the GitHub Actions workflow included with OpenBASIC).")
        intro.setWordWrap(True)
        lay.addWidget(intro)
        form = QFormLayout()
        self.name = QLineEdit(re.sub(r"[^\w\- ]", "", self.stem) or "MyProgram")
        self.out = QLineEdit(os.path.join(self.base_dir, f"{self.stem} app"))
        browse = QPushButton("Browse…")
        browse.clicked.connect(self.pick_out)
        row = QHBoxLayout()
        row.addWidget(self.out)
        row.addWidget(browse)
        form.addRow("App name:", self.name)
        form.addRow("Save to folder:", row)
        lay.addLayout(form)
        lay.addWidget(QLabel("Files to include (found in your program):"))
        self.files = QListWidget()
        src = main.current_editor().toPlainText()
        for rel in referenced_files(src, self.base_dir):
            it = QListWidgetItem(rel)
            it.setFlags(it.flags() | Qt.ItemIsUserCheckable)
            it.setCheckState(Qt.Checked)
            self.files.addItem(it)
        if self.files.count() == 0:
            it = QListWidgetItem("(no data files referenced)")
            it.setFlags(Qt.NoItemFlags)
            self.files.addItem(it)
        lay.addWidget(self.files, 1)
        add = QPushButton("Add files…")
        add.clicked.connect(self.add_files)
        self.whole = QCheckBox("Also copy everything else in the program's folder")
        r2 = QHBoxLayout()
        r2.addWidget(add)
        r2.addWidget(self.whole)
        r2.addStretch()
        lay.addLayout(r2)
        self.log = QPlainTextEdit()
        self.log.setReadOnly(True)
        self.log.setMaximumBlockCount(3000)
        lay.addWidget(self.log, 1)
        self.buttons = QDialogButtonBox()
        self.build_btn = self.buttons.addButton("Build", QDialogButtonBox.AcceptRole)
        self.buttons.addButton(QDialogButtonBox.Close)
        self.build_btn.clicked.connect(self.build)
        self.buttons.rejected.connect(self.reject)
        lay.addWidget(self.buttons)
        if find_runtime() is None:
            self.say("The first build prepares the OpenBASIC runtime for this computer. That takes a few "
                     "minutes once; later builds take seconds.")

    def say(self, text):
        self.log.appendPlainText(text)

    def pick_out(self):
        d = QFileDialog.getExistingDirectory(self, "Save app to", self.base_dir)
        if d:
            self.out.setText(os.path.join(d, f"{self.stem} app"))

    def add_files(self):
        fs, _ = QFileDialog.getOpenFileNames(self, "Add files", self.base_dir)
        for f in fs:
            rel = os.path.relpath(f, self.base_dir)
            if rel.startswith(".."):
                rel = os.path.basename(f)
            it = QListWidgetItem(rel)
            it.setData(Qt.UserRole, f)
            it.setFlags(it.flags() | Qt.ItemIsUserCheckable)
            it.setCheckState(Qt.Checked)
            self.files.addItem(it)

    def build(self):
        self.build_btn.setEnabled(False)
        rt = find_runtime()
        if rt is not None:
            self.assemble(rt)
            return
        try:
            import PyInstaller  # noqa: F401
        except ImportError:
            self.say("PyInstaller isn't installed, so the runtime can't be prepared.\n"
                     "Install it with:  pip install pyinstaller   then press Build again.")
            self.build_btn.setEnabled(True)
            return
        exe, args, self.work = pyinstaller_command()
        self.say("Preparing the runtime (one time only)…")
        self.proc = QProcess(self)
        self.proc.setProcessChannelMode(QProcess.MergedChannels)
        self.proc.readyReadStandardOutput.connect(
            lambda: self.say(bytes(self.proc.readAllStandardOutput()).decode(errors="replace").rstrip()))
        self.proc.finished.connect(self.runtime_built)
        self.proc.start(exe, args)

    def runtime_built(self, code, status):
        shutil.rmtree(getattr(self, "work", ""), ignore_errors=True)
        rt = find_runtime()
        if code != 0 or rt is None:
            self.say(f"Preparing the runtime failed (exit code {code}). See the messages above.")
            self.build_btn.setEnabled(True)
            return
        self.say("Runtime ready.")
        self.assemble(rt)

    def assemble(self, runtime):
        try:
            out = self.do_assemble(runtime)
        except OSError as e:
            self.say(f"Couldn't create the app: {e}")
            self.build_btn.setEnabled(True)
            return
        self.say(f"\nDone. Your app is in:\n{out}\n\nCopy that whole folder to share the program.")
        self.build_btn.setEnabled(True)

    def do_assemble(self, runtime):
        name = self.name.text().strip() or self.stem
        out = self.out.text().strip()
        os.makedirs(out, exist_ok=True)
        source = self.main.current_editor().toPlainText()
        packed = pack(source, os.path.basename(self.program))
        if IS_MAC:
            app = os.path.join(out, name + ".app")
            if os.path.exists(app):
                shutil.rmtree(app)
            shutil.copytree(runtime, app, symlinks=True)
            data_dir = os.path.join(app, "Contents", "Resources")
            exe_dir = os.path.join(app, "Contents", "MacOS")
            # the executable inside keeps its name; the .obp is found by being the only one
            plist = os.path.join(app, "Contents", "Info.plist")
            if os.path.exists(plist):
                txt = open(plist, encoding="utf-8").read()
                txt = txt.replace("<string>OpenBASICRuntime</string>", f"<string>{name}</string>", 1)
                open(plist, "w", encoding="utf-8").write(txt)
            target = os.path.join(data_dir, name + ".obp")
        else:
            exe_name = name + (".exe" if IS_WIN else "")
            dst = os.path.join(out, exe_name)
            shutil.copy2(runtime, dst)
            if not IS_WIN:
                os.chmod(dst, 0o755)
            data_dir = out
            target = os.path.join(out, name + ".obp")
        with open(target, "wb") as f:
            f.write(packed)
        self.say(f"Program packed into {os.path.basename(target)}")
        copied = 0
        for i in range(self.files.count()):
            it = self.files.item(i)
            if not (it.flags() & Qt.ItemIsUserCheckable) or it.checkState() != Qt.Checked:
                continue
            rel = it.text()
            src = it.data(Qt.UserRole) or os.path.join(self.base_dir, rel)
            dst = os.path.join(data_dir, rel)
            os.makedirs(os.path.dirname(dst), exist_ok=True)
            shutil.copy2(src, dst)
            copied += 1
        if self.whole.isChecked():
            for entry in os.listdir(self.base_dir):
                srcp = os.path.join(self.base_dir, entry)
                if os.path.abspath(srcp) == os.path.abspath(out) or entry.startswith("."):
                    continue
                dstp = os.path.join(data_dir, entry)
                if os.path.isdir(srcp):
                    shutil.copytree(srcp, dstp, dirs_exist_ok=True)
                else:
                    shutil.copy2(srcp, dstp)
                copied += 1
        self.say(f"Copied {copied} file(s)/folder(s) the program uses.")
        return out

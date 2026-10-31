"""Run every .bas file in a folder through OpenBASIC and report what failed.

    python tools/run_corpus.py path/to/programs [--seconds 3] [--shots shots_dir]

Each program runs in its own process (offscreen) with an automatic "user" that
dismisses dialogs and answers INPUT prompts, and is stopped after a few seconds.
Programs are run in a temporary copy of the folder, so nothing in it is changed.
"""
import argparse
import json
import os
import shutil
import subprocess
import sys
import tempfile
from collections import Counter

HERE = os.path.dirname(os.path.abspath(__file__))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("folder")
    ap.add_argument("--seconds", type=float, default=3)
    ap.add_argument("--shots", help="save a screenshot of each program's windows here")
    a = ap.parse_args()
    work = tempfile.mkdtemp(prefix="openbasic-corpus-")
    shutil.copytree(a.folder, work, dirs_exist_ok=True)
    env = dict(os.environ, QT_QPA_PLATFORM="offscreen")
    if a.shots:
        os.makedirs(a.shots, exist_ok=True)
        env["SHOT_DIR"] = os.path.abspath(a.shots)
    files = sorted(os.path.relpath(os.path.join(d, f), work)
                   for d, _, fs in os.walk(work) for f in fs if f.lower().endswith(".bas"))
    results = []
    for f in files:
        try:
            p = subprocess.run([sys.executable, os.path.join(HERE, "run_one.py"), f, str(a.seconds)],
                               cwd=work, env=env, capture_output=True, text=True, timeout=a.seconds + 30)
            line = next((l for l in p.stdout.splitlines() if l.startswith("RESULT ")), None)
            r = json.loads(line[7:]) if line else {"file": f, "status": "crash", "error": p.stderr[-400:]}
        except subprocess.TimeoutExpired:
            r = {"file": f, "status": "hang", "error": "didn't stop"}
        results.append(r)
        mark = "ok " if r["status"] in ("ended", "stopped") else "ERR"
        print(f"{mark} {f}" + ("" if mark == "ok " else f"  line {r.get('line')}: {r.get('error')}"), flush=True)
    shutil.rmtree(work, ignore_errors=True)
    print("\n" + ", ".join(f"{k}: {v}" for k, v in Counter(r["status"] for r in results).items()))
    return 0 if all(r["status"] in ("ended", "stopped") for r in results) else 1


if __name__ == "__main__":
    sys.exit(main())

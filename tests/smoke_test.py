#!/usr/bin/env python3
"""End-to-end check: start the server on the examples, wait for builds, edit a file, see it rebuild.

    python3 tests/smoke_test.py
Needs Tectonic and an internet connection the first time (Tectonic downloads LaTeX packages).
"""
import json
import os
import shutil
import subprocess
import sys
import tempfile
import time
import urllib.request

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PORT = 8791


def get(path):
    with urllib.request.urlopen(f"http://127.0.0.1:{PORT}{path}", timeout=5) as r:
        return r.read()


def status():
    return json.loads(get("/status.json"))


def wait(cond, what, timeout=240):
    end = time.time() + timeout
    while time.time() < end:
        try:
            v = cond()
            if v:
                return v
        except Exception:
            pass
        time.sleep(0.5)
    sys.exit(f"FAIL: timed out waiting for {what}")


tmp = tempfile.mkdtemp()
work = os.path.join(tmp, "multi")
shutil.copytree(os.path.join(ROOT, "examples", "multi"), work)
proc = subprocess.Popen([sys.executable, os.path.join(ROOT, "preview.py"), "--port", str(PORT)], cwd=work,
                        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
try:
    s = wait(lambda: (lambda d: d if len(d["order"]) == 2 and all(x["ok"] for x in d["docs"].values()) else None)(status()),
             "both documents to build")
    print("ok  found and built:", ", ".join(d["label"] for d in s["docs"].values()))
    ids = s["order"]
    by = {d["label"]: i for i, d in s["docs"].items()}
    rep, let = by["Quarterly Report"], by["Customer Letter"]
    assert get(f"/pdf/{rep}.pdf")[:5] == b"%PDF-", "not a PDF"
    print("ok  served a PDF")
    assert get("/")[:15].lower() == b"<!doctype html>"
    print("ok  served the viewer")

    before = {i: s["docs"][i]["version"] for i in ids}
    with open(os.path.join(work, "report", "report.tex"), "a") as f:
        f.write("\n% touched\n")
    wait(lambda: status()["docs"][rep]["version"] > before[rep], "the edited document to rebuild")
    time.sleep(1.5)
    assert status()["docs"][let]["version"] == before[let], "an unrelated document was rebuilt"
    print("ok  editing one document rebuilds only that document")

    before = {i: status()["docs"][i]["version"] for i in ids}
    with open(os.path.join(work, "shared", "style.tex"), "a") as f:
        f.write("\n% touched\n")
    wait(lambda: all(status()["docs"][i]["version"] > before[i] for i in ids), "the shared file to rebuild everything")
    print("ok  editing a shared file rebuilds every document")

    path = os.path.join(work, "letter", "letter.tex")
    with open(path) as f:
        src = f.read()
    with open(path, "w") as f:   # a broken command inside the document body
        f.write(src.replace("\\end{document}", "\\thisisnotacommand\n\\end{document}"))
    wait(lambda: status()["docs"][let]["ok"] is False, "the broken document to report an error")
    assert status()["docs"][let]["log"], "no error log"
    assert get(f"/pdf/{let}.pdf")[:5] == b"%PDF-", "last good PDF should still be served"
    print("ok  a broken document shows its error and keeps the last good PDF")
    print("\nAll checks passed.")
finally:
    proc.terminate()
    shutil.rmtree(tmp, ignore_errors=True)

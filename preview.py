#!/usr/bin/env python3
"""tectonic-live-preview: rebuild LaTeX with Tectonic on every save and see the PDF in your browser.

    python3 preview.py                       # every .tex document found under the current folder
    python3 preview.py report.tex            # one document
    python3 preview.py docs/ letters/        # several folders
    python3 preview.py --shared common/ .    # `common/` is shared: changing it rebuilds every document

Open http://localhost:8765. Full documentation: README.md
"""
import argparse
import http.server
import json
import os
import re
import shutil
import subprocess
import sys
import threading
import time
import webbrowser
from urllib.parse import parse_qs, urlparse

HERE = os.path.dirname(os.path.abspath(__file__))
WATCHED = {".tex", ".sty", ".cls", ".bib", ".bst", ".def", ".cfg", ".ltx", ".tikz",
           ".png", ".jpg", ".jpeg", ".svg", ".eps", ".csv", ".dat", ".txt"}
SKIP_DIRS = {"build", ".git", "node_modules", "__pycache__", ".venv", "venv", ".idea", ".vscode"}
NOISE = ("Requested font", "->")            # noisy font lines in Tectonic's output

lock = threading.Lock()
docs = {}          # slug -> {label, tex, dir, pdf}
status = {}        # slug -> build state, served as JSON
shared_dirs = []   # directories whose files affect every document
group_order = []   # dropdown entries (empty = no groups configured)
settings = {}


# ----------------------------------------------------------------------------- discovery
def is_document(path):
    """A LaTeX document (not a fragment or a package) contains \\documentclass near the top."""
    try:
        with open(path, encoding="utf-8", errors="ignore") as f:
            return bool(re.search(r"^[^%\n]*\\documentclass", f.read(8192), re.M))
    except OSError:
        return False


def find_documents(paths, exclude):
    found = []
    for p in paths:
        p = os.path.abspath(p)
        if os.path.isfile(p):
            found.append(p)
            continue
        for dirpath, dirnames, files in os.walk(p):
            dirnames[:] = sorted(d for d in dirnames if d not in SKIP_DIRS and d not in exclude)
            for name in sorted(files):
                if name.endswith(".tex") and is_document(os.path.join(dirpath, name)):
                    found.append(os.path.join(dirpath, name))
    seen, unique = set(), []
    for f in found:
        if f not in seen:
            seen.add(f)
            unique.append(f)
    return unique


def make_label(tex, all_tex):
    stem = os.path.splitext(os.path.basename(tex))[0]
    same = [t for t in all_tex if os.path.splitext(os.path.basename(t))[0] == stem]
    name = stem if len(same) == 1 else os.path.basename(os.path.dirname(tex)) + " / " + stem
    return re.sub(r"[-_]+", " ", name).strip().title() if name == name.lower() else name


def make_slug(tex, base, used):
    rel = os.path.relpath(tex, base)
    slug = re.sub(r"[^a-z0-9]+", "-", os.path.splitext(rel)[0].lower()).strip("-") or "doc"
    n, unique = 2, slug
    while unique in used:
        unique, n = f"{slug}-{n}", n + 1
    used.add(unique)
    return unique


def load_config(path):
    if not path:
        return {}
    with open(path, encoding="utf-8") as f:
        return json.load(f)


# ----------------------------------------------------------------------------- building
def snapshot():
    """{path: mtime} for every watched file under a document folder or a shared folder."""
    roots = {d["dir"] for d in docs.values()} | set(shared_dirs)
    # skip roots that live inside another root, they are already walked
    roots = {r for r in roots if not any(r != o and r.startswith(o + os.sep) for o in roots)}
    mtimes = {}
    for root in roots:
        for dirpath, dirnames, files in os.walk(root):
            dirnames[:] = [d for d in dirnames if d not in SKIP_DIRS]
            for name in files:
                if os.path.splitext(name)[1].lower() in WATCHED:
                    path = os.path.join(dirpath, name)
                    try:
                        mtimes[path] = os.stat(path).st_mtime
                    except OSError:
                        pass
    return mtimes


def affected(changed):
    """The document whose folder is the closest parent of a changed file; shared files hit everything."""
    hit = set()
    for path in changed:
        owners = [(len(d["dir"]), s) for s, d in docs.items()
                  if path.startswith(d["dir"] + os.sep)]
        if any(path.startswith(sd + os.sep) for sd in shared_dirs) and not owners:
            hit.update(docs)
        elif owners:
            deepest = max(length for length, _ in owners)
            hit.update(s for length, s in owners if length == deepest)
        else:
            hit.update(docs)
    return [s for s in docs if s in hit]


def build(slug):
    d = docs[slug]
    out = os.path.join(d["dir"], "build")
    os.makedirs(out, exist_ok=True)
    with lock:
        status[slug]["building"] = True
    started = time.time()
    cmd = ["tectonic", "--keep-logs", "--outdir", out] + settings["engine_args"] + [os.path.basename(d["tex"])]
    proc = subprocess.run(cmd, cwd=d["dir"], capture_output=True, text=True)
    ok = proc.returncode == 0
    if ok and settings["copy_pdf"]:
        shutil.copyfile(d["pdf"], os.path.join(d["dir"], os.path.basename(d["pdf"])))
    log = "\n".join(l for l in (proc.stdout + proc.stderr).splitlines() if not any(n in l for n in NOISE))
    with lock:
        st = status[slug]
        st.update(ok=ok, building=False, log=log[-12000:], built_at=time.strftime("%H:%M:%S"),
                  seconds=round(time.time() - started, 1))
        st["version"] += 1
    print(f"[{st['built_at']}] {slug}: {'ok' if ok else 'FAILED'} in {st['seconds']}s", flush=True)


def watch():
    last = None
    while True:
        snap = snapshot()
        if last is None:
            todo = list(docs)
        else:
            changed = [p for p in snap if snap[p] != last.get(p)] + [p for p in last if p not in snap]
            todo = affected(changed) if changed else []
        last = snap
        for slug in todo:
            build(slug)
        time.sleep(settings["interval"])


# ----------------------------------------------------------------------------- server
class Handler(http.server.BaseHTTPRequestHandler):
    def send(self, code, body, ctype, extra=None):
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        for k, v in (extra or {}).items():
            self.send_header(k, v)
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        url = urlparse(self.path)
        path = url.path
        if path == "/":
            with open(os.path.join(HERE, "viewer.html"), "rb") as f:
                return self.send(200, f.read(), "text/html; charset=utf-8")
        if path == "/status.json":
            with lock:
                for slug, d in docs.items():
                    status[slug]["bw"] = bool(d["bw"] and os.path.isfile(d["bw"]))
                body = json.dumps({"title": settings["title"], "order": list(docs), "groups": group_order,
                                   "default": settings["default"], "docs": status}).encode()
            return self.send(200, body, "application/json")
        if path.startswith("/pdf/") and path.endswith(".pdf"):
            doc = docs.get(path[len("/pdf/"):-len(".pdf")])
            query = parse_qs(url.query)
            pdf = doc and (doc["bw"] if "bw" in query else doc["pdf"])   # ?bw=1 -> the ready-made black-and-white copy
            if pdf and os.path.isfile(pdf):
                extra = {}
                if "dl" in query:
                    extra["Content-Disposition"] = f'attachment; filename="{os.path.basename(pdf)}"'
                with open(pdf, "rb") as f:
                    return self.send(200, f.read(), "application/pdf", extra)
        self.send(404, b"Not found", "text/plain")

    def log_message(self, *args):
        pass


# ----------------------------------------------------------------------------- main
def main():
    ap = argparse.ArgumentParser(
        prog="preview.py",
        description="Rebuild LaTeX with Tectonic on every save and preview the PDF in the browser.")
    ap.add_argument("paths", nargs="*", default=["."],
                    help=".tex files or folders to scan for documents (default: the current folder)")
    ap.add_argument("-p", "--port", type=int, default=None, help="port to serve on (default 8765)")
    ap.add_argument("--host", default=None, help="address to bind (default 127.0.0.1; use 0.0.0.0 to share on your network)")
    ap.add_argument("-s", "--shared", action="append", default=[], metavar="DIR",
                    help="folder of shared files (preamble, images); changes rebuild every document. Repeatable")
    ap.add_argument("-x", "--exclude", action="append", default=[], metavar="NAME",
                    help="folder name to skip when scanning. Repeatable")
    ap.add_argument("--copy-pdf", action="store_true", default=None,
                    help="also copy each finished PDF next to its .tex file")
    ap.add_argument("--title", default=None, help="page title (default: 'TeX Live Preview')")
    ap.add_argument("--open", dest="open_browser", action="store_true", default=None, help="open the browser on start")
    ap.add_argument("--engine-args", default=None, metavar="ARGS",
                    help='extra Tectonic arguments, for example "--only-cached" (quote them)')
    ap.add_argument("--interval", type=float, default=None, help="seconds between file checks (default 0.4)")
    ap.add_argument("--config", default=None, metavar="FILE",
                    help="JSON settings file (default: preview.json in the current folder, if present)")
    ap.add_argument("--select", default=None, metavar="ID", help="document to show first (its id, see the tab address)")
    args = ap.parse_args()

    if not shutil.which("tectonic"):
        sys.exit("Tectonic is not installed. Install it first: https://tectonic-typesetting.github.io/install.html\n"
                 "  macOS: brew install tectonic")

    cfg_path = args.config or ("preview.json" if os.path.isfile("preview.json") else None)
    cfg = load_config(cfg_path)
    pick = lambda cli, key, default: cli if cli is not None else cfg.get(key, default)
    settings.update(
        port=pick(args.port, "port", 8765), host=pick(args.host, "host", "127.0.0.1"),
        copy_pdf=bool(pick(args.copy_pdf, "copyPdf", False)), title=pick(args.title, "title", "TeX Live Preview"),
        interval=pick(args.interval, "interval", 0.4), default=pick(args.select, "select", None),
        open_browser=bool(pick(args.open_browser, "open", False)),
        engine_args=(args.engine_args.split() if args.engine_args is not None else cfg.get("engineArgs", [])),
    )
    base = os.path.dirname(os.path.abspath(cfg_path)) if cfg_path else os.getcwd()
    paths = args.paths if (args.paths != ["."] or not cfg.get("paths")) else [os.path.join(base, p) for p in cfg["paths"]]
    exclude = set(args.exclude) | set(cfg.get("exclude", []))
    shared_dirs.extend(os.path.abspath(p) for p in args.shared)
    shared_dirs.extend(os.path.abspath(os.path.join(base, p)) for p in cfg.get("shared", []))
    labels = {os.path.abspath(os.path.join(base, k)): v for k, v in cfg.get("labels", {}).items()}
    # "bw": {"doc.tex": "path/to/doc-bw.pdf"}; adds a B&W button for documents whose copy exists
    bw_pdfs = {os.path.abspath(os.path.join(base, k)): os.path.abspath(os.path.join(base, v)) for k, v in cfg.get("bw", {}).items()}
    # "groups": {"folder": "Dropdown name"}; a document belongs to the first folder that contains it
    groups = [(os.path.abspath(os.path.join(base, k)), v) for k, v in cfg.get("groups", {}).items()]

    found = find_documents(paths, exclude)
    if not found:
        sys.exit("No LaTeX documents found (looking for .tex files that contain \\documentclass).")
    used = set()
    for tex in found:
        slug = make_slug(tex, os.getcwd(), used)
        d = os.path.dirname(tex)
        group = next((name for folder, name in groups if tex.startswith(folder + os.sep)), "Other" if groups else None)
        docs[slug] = {"label": labels.get(tex) or make_label(tex, found), "tex": tex, "dir": d,
                      "pdf": os.path.join(d, "build", os.path.splitext(os.path.basename(tex))[0] + ".pdf"),
                      "bw": bw_pdfs.get(tex)}
        status[slug] = {"label": docs[slug]["label"], "group": group, "version": 0, "ok": None, "building": False,
                        "log": "", "built_at": None, "seconds": None}
    group_order[:] = [n for n in dict.fromkeys([n for _, n in groups] + ["Other"]) if any(s["group"] == n for s in status.values())]
    if settings["default"] and settings["default"] not in docs:
        sys.exit(f"Unknown document id '{settings['default']}'. Available: {', '.join(docs)}")

    threading.Thread(target=watch, daemon=True).start()
    url = f"http://{'localhost' if settings['host'] == '127.0.0.1' else settings['host']}:{settings['port']}"
    print(f"Previewing {len(docs)} document(s) on {url}", flush=True)
    for slug, d in docs.items():
        print(f"  {slug:28s} {os.path.relpath(d['tex'])}", flush=True)
    if settings["open_browser"]:
        webbrowser.open(url)
    try:
        http.server.ThreadingHTTPServer((settings["host"], settings["port"]), Handler).serve_forever()
    except OSError as e:
        sys.exit(f"Could not start the server on port {settings['port']}: {e}. Try --port <other number>.")
    except KeyboardInterrupt:
        print("\nStopped.")


if __name__ == "__main__":
    main()

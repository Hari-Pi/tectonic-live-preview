# tectonic-live-preview

Edit LaTeX, save, and watch the PDF update in your browser. No editor plugin, no LaTeX installation: it uses [Tectonic](https://tectonic-typesetting.github.io) to build and a tiny built-in web page to show the result.

- **Live:** every save rebuilds the document and refreshes the page, keeping your scroll position.
- **One or many documents:** point it at a file or a whole folder. Several documents get tabs.
- **Smart rebuilds:** editing one document rebuilds only that document. Editing a shared preamble or image rebuilds all of them.
- **Errors are readable:** if a build fails, the log is shown and the last good PDF stays on screen.
- **Nothing to install** except Tectonic and Python 3. No packages, no build step, one Python file and one HTML file.

```
your .tex files  ──►  preview.py (watches, runs Tectonic, serves)  ──►  browser tab with the PDF
```

## Quick start

1. Install Tectonic (macOS shown; see [other systems](https://tectonic-typesetting.github.io/install.html)):

   ```bash
   brew install tectonic
   ```

2. Get this tool:

   ```bash
   git clone https://github.com/Hari-Pi/tectonic-live-preview.git
   ```

3. Run it on your document (or folder):

   ```bash
   python3 tectonic-live-preview/preview.py my-paper.tex
   ```

4. Open <http://localhost:8765>. Edit `my-paper.tex`, save, and the page updates.

The first build downloads the LaTeX packages your document needs, so it needs internet once and can take a minute. Later builds take a second or less.

## Using it

```bash
python3 preview.py                          # every document found under the current folder
python3 preview.py report.tex               # one document
python3 preview.py papers/ letters/         # several folders
python3 preview.py --shared common/ .       # common/ holds shared files, see below
python3 preview.py --open --port 9000 .     # open the browser, use another port
```

A **document** is any `.tex` file that contains `\documentclass`. Files without it (chapters, preambles brought in with `\input`) are not shown on their own.

### Shared files

If several documents use the same preamble, logo or style file, keep them in one folder and tell the previewer:

```bash
python3 preview.py --shared common/ .
```

Now a change inside `common/` rebuilds every document, while a change inside one document's own folder rebuilds only that document.

### Command-line options

| Option | Meaning |
|---|---|
| `PATH ...` | `.tex` files or folders to scan (default: the current folder) |
| `-p`, `--port N` | Port to serve on (default `8765`) |
| `--host ADDR` | Address to listen on (default `127.0.0.1`, this computer only; `0.0.0.0` shares it on your network) |
| `-s`, `--shared DIR` | Shared folder; changes rebuild every document. Repeatable |
| `-x`, `--exclude NAME` | Folder name to skip while scanning. Repeatable |
| `--copy-pdf` | Also copy each finished PDF next to its `.tex` file |
| `--title TEXT` | Browser tab title |
| `--open` | Open the browser on start |
| `--select ID` | Document to show first |
| `--engine-args "..."` | Extra Tectonic arguments, for example `"--only-cached"` |
| `--interval SEC` | How often to look for saved changes (default `0.4`) |
| `--config FILE` | Settings file (default: `preview.json` in the current folder, if it exists) |

Every option can also live in a `preview.json`, which is handy for a project you open often. See [docs/configuration.md](docs/configuration.md).

Many documents for different clients or colleges? Add `"groups"` to `preview.json` and the page gets a dropdown to pick one group at a time, instead of one long row of tabs. See [Groups](docs/configuration.md#groups).

### In the browser

- **Group dropdown** (only when `groups` is configured) picks which set of documents the tabs show.
- **Tabs** switch between documents. The dot on a tab shows its build state: green is good, amber is building, red means the last build failed.
- **B&W** toggle (only when the `bw` setting points at a copy) switches the page, and the **PDF** download, between colour and black and white. It remembers your choice.
- **+ / −** zoom. **PDF** downloads the document you are looking at.
- The address shows the current document (for example `#report`), so you can bookmark or share a link to it.
- If a build fails, the error log appears at the top and the previous PDF stays visible.

## Where the files go

For a document `docs/paper.tex`:

| File | What it is |
|---|---|
| `docs/build/paper.pdf` | The PDF (rewritten on every good build) |
| `docs/build/paper.log` | The LaTeX log, useful when you need details |
| `docs/paper.pdf` | Only with `--copy-pdf`: a copy next to the source |

Add `build/` to your `.gitignore`.

## Use it in many projects

The tool is one folder, so there is nothing to install per project. Two easy ways:

- **Keep one copy** and always run it by path, for example add this to `~/.zshrc`:

  ```bash
  alias texpreview='python3 ~/Projects/tectonic-live-preview/preview.py'
  ```

  Then, in any project: `texpreview .` or `texpreview thesis.tex`.
- **Or vendor it** into a repository (copy `preview.py` and `viewer.html` into a `tools/` folder, or add this repository as a git submodule).

Working with Claude Code or another launcher that reads `.claude/launch.json`? See [docs/how-it-works.md](docs/how-it-works.md#launching-from-an-editor-or-claude-code).

## Try the examples

```bash
python3 preview.py examples/single/hello.tex
cd examples/multi && python3 ../../preview.py     # two documents sharing a preamble
```

## Troubleshooting

| Problem | What to do |
|---|---|
| `Tectonic is not installed` | Install it: `brew install tectonic` or see the [install page](https://tectonic-typesetting.github.io/install.html) |
| First build is slow or fails offline | Tectonic downloads packages the first time. Connect to the internet once, then it works from its cache |
| `Could not start the server on port 8765` | Something else uses that port. Choose another: `--port 9000` |
| The page says "Preview server not reachable" | The command was stopped. Run it again |
| Blank page or no PDF drawn | The page loads its PDF viewer from a CDN, so it needs internet. See [how it works](docs/how-it-works.md#offline-use) |
| A document is not listed | It needs `\documentclass` near the top, and its folder must not be `build`, `.git` or `node_modules` (or excluded with `-x`) |
| Fonts look different from the PDF | The page draws the PDF itself. Download it with the **PDF** button to see the real file |
| Changes are not picked up | Only these file types are watched: `.tex .sty .cls .bib .bst .def .cfg .ltx .tikz .png .jpg .jpeg .svg .eps .csv .dat .txt`, inside the document's folder or a `--shared` folder |

## Test it

```bash
python3 tests/smoke_test.py
```

This starts the previewer on the examples, edits files, and checks that documents are found, built, served, and rebuilt correctly, including the error case.

## Limits

- Built for **Tectonic**. Other engines (`latexmk`, `xelatex`) are not wired in.
- It builds **sequentially**. Many large documents rebuilt at once take as long as their builds add up to.
- It is a local convenience tool with **no authentication**. Keep it on `127.0.0.1` unless you trust your network.

## License

MIT. See [LICENSE](LICENSE).

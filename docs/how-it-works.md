# How it works

The whole tool is two files:

| File | Role |
|---|---|
| `preview.py` | Finds documents, watches for saves, runs Tectonic, and serves the page and the PDFs. Python 3 standard library only |
| `viewer.html` | The page. Asks the server what is built, then draws PDFs with [PDF.js](https://mozilla.github.io/pdf.js/) |

```
                 every 0.4 s
 .tex files  ◄────────────────  watcher thread  ──►  tectonic  ──►  build/<name>.pdf
                                      │
                                      ▼   status (version, ok, log, time)
 browser  ◄──── viewer.html ◄──── HTTP server ◄──── PDF file
     │              polls /status.json every 0.8 s
     └── draws /pdf/<id>.pdf when its version changes
```

## The build loop

1. On start, the previewer **scans** the paths for `.tex` files containing `\documentclass`, skipping `build`, `.git`, `node_modules` and similar folders.
2. A **watcher** thread records the modification time of every watched file under each document's folder and each shared folder.
3. About every 0.4 seconds it compares. Changed files are mapped to the documents they affect (see [which documents rebuild](configuration.md#which-documents-rebuild)).
4. Each affected document is built with `tectonic --keep-logs --outdir <folder>/build <file>.tex`, run from the document's folder so relative `\input` and `\includegraphics` paths work.
5. The result is stored: `ok`, a `version` number that goes up after every build, the time taken, and the cleaned build log.

## What the page does

- Polls `/status.json`. When the visible document's `version` changes and its build succeeded, it downloads `/pdf/<id>.pdf?v=<version>` and redraws the pages, then puts you back where you were scrolling.
- Remembers each tab's scroll position and your last tab in the browser (with a safe fallback if storage is blocked).
- On a failed build it shows the log and leaves the last good PDF in place, because the old file in `build/` is not deleted until a new one succeeds.

## The HTTP interface

Bound to `127.0.0.1` by default.

| Path | Returns |
|---|---|
| `/` | The page (`viewer.html`) |
| `/status.json` | `{ title, order, default, docs: { id: { label, version, ok, building, log, built_at, seconds } } }` |
| `/pdf/<id>.pdf` | The current PDF of a document |
| `/pdf/<id>.pdf?dl=1` | The same, as a download |

Only these paths are served. The source `.tex` files are never exposed.

## Offline use

The page loads PDF.js from a CDN (`cdnjs.cloudflare.com`), so it needs internet. To use it fully offline, download `pdf.min.js` and `pdf.worker.min.js` (version 3.11.174), place them next to `viewer.html`, and change the two URLs at the top of the script in `viewer.html` to point at them. The server only serves fixed paths, so also add routes for those two files in `Handler.do_GET`, or open `viewer.html` from a small static server of your own.

## Launching from an editor or Claude Code

Any launcher that runs a command and opens a port will do. For tools that read a `.claude/launch.json`:

```json
{
  "version": "0.0.1",
  "configurations": [
    {
      "name": "tex-preview",
      "runtimeExecutable": "python3",
      "runtimeArgs": ["tools/tectonic-live-preview/preview.py", "--shared", "common", "docs"],
      "port": 8765
    }
  ]
}
```

VS Code users can add a task that runs the same command, then open `http://localhost:8765` in the Simple Browser.

## Design notes

- **Polling instead of file-system events.** It works the same on macOS, Linux and Windows, needs no dependency, and is cheap because it only compares file times.
- **Sequential builds.** One build at a time keeps output readable and avoids two Tectonic runs fighting over the package cache.
- **Build output stays beside the source.** `build/` inside each document's folder means relative paths just work and nothing outside your project is touched.
- **Separate `--shared` folders.** Without them the tool cannot know that a preamble in another folder should rebuild everything, and guessing from `\input` lines is unreliable.

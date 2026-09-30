# Configuration

Everything can be set on the command line. For a project you open often, put the settings in a **`preview.json`** and just run `python3 /path/to/preview.py`.

The previewer reads `preview.json` from the folder you run it in, or from a file you name with `--config`. Command-line options win over the file. Relative paths in the file are relative to the file itself.

## Example

```json
{
  "port": 8765,
  "title": "My Project Preview",
  "paths": ["papers", "letters"],
  "shared": ["common"],
  "exclude": ["archive", "drafts"],
  "labels": {
    "papers/thesis.tex": "Thesis",
    "letters/offer.tex": "Offer Letter"
  },
  "copyPdf": false,
  "open": true,
  "select": "papers-thesis",
  "engineArgs": []
}
```

## All settings

| Key | Type | Default | Same as | Meaning |
|---|---|---|---|---|
| `port` | number | `8765` | `--port` | Port to serve on |
| `host` | text | `"127.0.0.1"` | `--host` | Address to listen on |
| `title` | text | `"TeX Live Preview"` | `--title` | Browser tab title |
| `paths` | list | the folder holding the file | positional `PATH` | Files or folders to scan for documents |
| `shared` | list | none | `--shared` | Folders whose files affect every document |
| `exclude` | list | none | `--exclude` | Folder names to skip while scanning |
| `labels` | object | derived from file names | none | Tab names, keyed by the path of the `.tex` file |
| `copyPdf` | true/false | `false` | `--copy-pdf` | Copy each PDF next to its source |
| `open` | true/false | `false` | `--open` | Open the browser on start |
| `select` | text | first document | `--select` | Id of the document to show first |
| `engineArgs` | list | none | `--engine-args` | Extra arguments passed to Tectonic |
| `interval` | number | `0.4` | `--interval` | Seconds between checks for saved changes |

## Document ids

Each document gets an **id** from its path, lowercased with anything other than letters and digits turned into `-`:

| File | Id |
|---|---|
| `hello.tex` | `hello` |
| `papers/thesis.tex` | `papers-thesis` |
| `Reports/Q3 Summary.tex` | `reports-q3-summary` |

The id appears in the address (`http://localhost:8765/#papers-thesis`) and is what `select` and `--select` use.

## Tab names

Unless you give a label, the tab name comes from the file name: `my-thesis.tex` becomes **My Thesis**. If two documents have the same file name, the folder is added: **papers / main**.

## Which documents rebuild

| You save... | Rebuilt |
|---|---|
| A file in a document's own folder | That document (the one with the closest folder) |
| A file in a `shared` folder | Every document |
| A file that belongs to no document folder and no shared folder | Nothing (it is not watched) |

Two documents in the **same** folder rebuild together, because they cannot be told apart by folder. Put documents in their own folders if you want them independent.

## Watched file types

`.tex .sty .cls .bib .bst .def .cfg .ltx .tikz .png .jpg .jpeg .svg .eps .csv .dat .txt`. The `build/` folder is never watched, so the PDFs it produces cannot trigger another build.

## Passing options to Tectonic

Anything Tectonic accepts can be added, for example to build without touching the network once packages are cached:

```bash
python3 preview.py --engine-args "--only-cached" report.tex
```

or in `preview.json`: `"engineArgs": ["--only-cached"]`.

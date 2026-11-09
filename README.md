# html-duplicate-id-checker-cli

Find duplicate id attributes in HTML, fail CI when an id appears twice.

[![CI](https://github.com/haiderstudio/html-duplicate-id-checker-cli/actions/workflows/ci.yml/badge.svg)](https://github.com/haiderstudio/html-duplicate-id-checker-cli/actions/workflows/ci.yml) [![Licence: MIT](https://img.shields.io/badge/Licence-MIT-yellow.svg)](LICENSE)

## What it does

`html_duplicate_id_checker` reads HTML files and finds every
`id` attribute value that appears twice in the same file, and
reports each one with the file, the id, and every element tag
and line number it appears on. It exits 1 when any duplicate
is found, so it can fail a CI run. A file with all-unique ids
exits 0.

- A duplicate id breaks real things: an anchor link
  (`#section`) jumps to the first element with that id,
  `getElementById` returns the wrong element, and a `<label
  for="...">` points at the wrong field. HTML says every id
  must be unique in a document, but nothing stops you typing
  the same id twice — this catches it before the page ships.
- Matching is case-sensitive, the way HTML ids work: `Main`
  and `main` are different ids and pass. The same id in two
  different files is not a duplicate — ids only have to be
  unique inside one document.
- An id inside an HTML comment does not count, and neither
  does text inside `<script>` or `<style>` blocks: only real
  elements count. A `getElementById("main")` call in a script
  is not an element with that id.
- Single-quoted, double-quoted, and unquoted ids are all
  found, and so is an uppercase `ID` attribute. An empty
  `id=""` is ignored: it is not a duplicate, it is a missing
  id, and that is a different check.
- A file given directly on the command line is always
  checked, whatever its name. A folder is walked for `.html`
  and `.htm` files, recursively by default (`--no-recursive`
  stops at the top level). `.git` folders are never walked,
  and directory links are never followed.
- `--json` prints the result as JSON (the human-readable
  lines go to standard error), and `--stdin` checks one
  HTML document read from standard input.

## Who it is for

Anyone who owns a website and wants every page's ids to be
unique — front-end developers, teams that review each
other's templates, and anyone who has ever clicked an anchor
link that landed on the wrong section.

## What it does NOT do

- It does not check whether an id *exists* — a missing
  anchor target is a different check. This tool only checks
  that the ids that are there appear once each.
- It does not check whether an id is a good name, and it
  does not check any other attribute. It checks `id` only.
- It does not fetch a live site, and it never rewrites a
  file. It is report-only, and it never touches the network.

## How this differs

- nedal-dev/idraaak-article-anchor-checker (0 stars) is a
  Sublime Text utility that finds missing fragment targets
  and duplicate ids — an editor plugin you click, not a
  command-line gate you run in CI. This tool is a tested
  command-line gate with a CI exit code, folder walking,
  and file-and-line reporting.
- arosenbach/dom-duplicate-ids-checker (1 star) checks
  duplicate ids in a live DOM, and nilskummert/
  HTML-Duplicate-ID-Check (0 stars) scans one webpage —
  both need a page to load. This tool checks local files,
  offline, before anything is deployed.
- dutrapedro/find_identicals (0 stars) scans HTML
  documents for duplicate id attributes as a one-off
  script, with no tests and no CI claim. This tool is a
  tested CLI with folder walking, `--json`/`--stdin`,
  and a fixed, documented rule.
- aim42/htmlSanityCheck-gradle-plugin (1 star) checks
  duplicate ids as one of many HTML checks inside a
  Gradle build. This tool does the one job, with nothing
  to build and nothing to install.
- Repo #50, html-title-checker-cli, checks the `<title>`;
  duplicate ids are a different check on the same files.

## Install

```sh
git clone https://github.com/haiderstudio/html-duplicate-id-checker-cli.git
cd html-duplicate-id-checker-cli
```

There is nothing else to install: Python 3.10 or newer,
standard library only, no dependencies.

## Usage

Check one HTML file:

```sh
python3 src/html_duplicate_id_checker.py page.html
```

A file with all-unique ids passes:

```sh
$ python3 src/html_duplicate_id_checker.py examples/good.html
OK — 1 file(s) checked, all ids are unique.
```

A file with a duplicate id fails, with the tags and lines:

```sh
$ python3 src/html_duplicate_id_checker.py examples/bad.html
FAIL examples/bad.html: duplicate id "main" — div line 7, section line 10
FAIL examples/bad.html: duplicate id "intro" — p line 11, div line 13
Checked 1 file(s), 2 problem(s) in 1 file(s).
```

Check a whole folder (HTML files only):

```sh
$ python3 src/html_duplicate_id_checker.py examples/
FAIL examples/bad.html: duplicate id "main" — div line 7, section line 10
FAIL examples/bad.html: duplicate id "intro" — p line 11, div line 13
Checked 3 file(s), 2 problem(s) in 1 file(s).
```

The same id in two different files is not a duplicate —
`examples/other.html` also uses `id="main"`, and the folder
run above still passes it.

Check one document from standard input:

```sh
$ python3 src/html_duplicate_id_checker.py --stdin < examples/bad.html
FAIL <stdin>: duplicate id "main" — div line 7, section line 10
FAIL <stdin>: duplicate id "intro" — p line 11, div line 13
Checked 1 file(s), 2 problem(s) in 1 file(s).
```

Machine-readable output:

```sh
$ python3 src/html_duplicate_id_checker.py --json examples/bad.html
{
  "files": [
    {
      "path": "examples/bad.html",
      "duplicates": [
        {
          "id": "main",
          "occurrences": [
            {
              "tag": "div",
              "line": 7
            },
            {
              "tag": "section",
              "line": 10
            }
          ]
        },
        {
          "id": "intro",
          "occurrences": [
            {
              "tag": "p",
              "line": 11
            },
            {
              "tag": "div",
              "line": 13
            }
          ]
        }
      ],
      "error": null
    }
  ],
  "checked": 1,
  "problems": 2
}
```

Exit codes: 0 when every id is unique, 1 when any duplicate
is found or a file cannot be read, 2 for a usage error (a
missing path, a bad flag, or no HTML files found).

## Examples

An id inside a comment is not a duplicate — the commented-out
`<p id="intro">` in `examples/good.html` is ignored, and so
is the `getElementById("main")` call inside the `<script>` in
`examples/bad.html`:

```sh
$ python3 src/html_duplicate_id_checker.py examples/good.html
OK — 1 file(s) checked, all ids are unique.
```

Case matters — `id="Main"` and `id="main"` in
`examples/bad.html` are different ids, so only the two real
duplicates are reported, not a third:

```sh
$ python3 src/html_duplicate_id_checker.py examples/bad.html
FAIL examples/bad.html: duplicate id "main" — div line 7, section line 10
FAIL examples/bad.html: duplicate id "intro" — p line 11, div line 13
Checked 1 file(s), 2 problem(s) in 1 file(s).
```

Run every bundled example at once with `sh
examples/run-example.sh` — the output is saved in
[examples/sample-output.md](examples/sample-output.md).

## How it is tested

```sh
python3 tests/test_html_duplicate_id_checker.py
```

The tests cover id parsing (double-quoted, single-quoted,
and unquoted ids, uppercase `ID` attributes, empty ids
ignored, ids with spaces treated as one value, ids inside
comments, `<script>`, and `<style>` ignored, self-closing
and nested tags, unclosed tags, a tag with two `id`
attributes), the duplicate check itself (same id twice
with exact tags and lines, three occurrences, several
duplicates in first-appearance order, case-sensitive
matching), the CLI (exit 0/1/2, folder walking, `.html`
and `.htm` only, `.git` skipped, `--no-recursive`,
`--exclude`, a direct file checked even without an HTML
name, `--stdin`, `--json` output, `--version`, bad flags,
missing paths, empty folders, a non-UTF-8 file reported,
input files left unchanged), the bundled examples
(sample output compared byte-for-byte against a fresh
run, and the README-quoted outputs checked against it),
and hygiene checks (no placeholder text, no absolute
paths, stdlib imports only, `.env` first in
`.gitignore`, CI file runs the test file).

## Contributing

Small, focused improvements are welcome — see [CONTRIBUTING.md](CONTRIBUTING.md).

## Licence

MIT — see [LICENSE](LICENSE).

## Original work

This tool was written from scratch for this repo. The idea
of checking duplicate ids is not new — the similar tools
named above (the Sublime plugin, the DOM checker, the
one-off scripts) are listed in "How this differs" — but
every line of code here is original, and the tool builds on
nothing but Python's standard library.

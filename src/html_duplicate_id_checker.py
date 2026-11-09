#!/usr/bin/env python3
"""Find duplicate id attributes in HTML files, fail CI when an id appears twice.

Run: python3 src/html_duplicate_id_checker.py page.html
     python3 src/html_duplicate_id_checker.py site/
     python3 src/html_duplicate_id_checker.py --stdin < page.html

A duplicate id breaks real things: an anchor link (#section) jumps
to the first element with that id, getElementById returns the wrong
element, and a <label for="..."> points at the wrong field. HTML
says every id must be unique in a document, but nothing stops you
typing the same id twice — this tool catches it before the page
ships, instead of after a user clicks a link that goes nowhere.

It reads one or more HTML files, records every id attribute with
the element tag and line number, and reports each id that appears
more than once in the same file, with the file, the id, and every
tag and line it appears on. It exits 1 when any duplicate is
found, so it can fail a CI run. A file with all-unique ids
exits 0.

Matching is case-sensitive, the way HTML ids work: "Main" and
"main" are different ids and pass. The same id in two different
files is not a duplicate — ids only have to be unique inside one
document. An id inside an HTML comment does not count, and
neither does text inside <script> or <style> blocks: only real
elements count. Single-quoted, double-quoted, and unquoted ids
are all found, and so is an uppercase ID attribute. An empty
id="" is ignored: it is not a duplicate, it is a missing id,
and that is a different check.

It never rewrites a file, never touches the network, and reads
only the files and folders you point it at.
"""

import argparse
import fnmatch
import json
import os
import sys
from html.parser import HTMLParser
from pathlib import Path

__version__ = "1.0.0"

HTML_EXTENSIONS = {".html", ".htm"}


class _IdCollector(HTMLParser):
    """Collect (tag, id value, line) for every id attribute seen."""

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.occurrences = []

    def handle_starttag(self, tag, attrs):
        line, _ = self.getpos()
        for name, value in attrs:
            if name == "id" and value:
                self.occurrences.append((tag, value, line))

    def handle_startendtag(self, tag, attrs):
        self.handle_starttag(tag, attrs)


def find_duplicates(text):
    """Return a list of duplicate ids in one HTML document.

    Each entry is {"id": str, "occurrences": [{"tag": str, "line": int}]}.
    Entries are in order of first appearance; occurrences are in
    document order. Ids are matched case-sensitively.
    """
    collector = _IdCollector()
    collector.feed(text)
    collector.close()
    seen = {}
    order = []
    for tag, value, line in collector.occurrences:
        if value not in seen:
            seen[value] = []
            order.append(value)
        seen[value].append({"tag": tag, "line": line})
    return [
        {"id": value, "occurrences": seen[value]}
        for value in order
        if len(seen[value]) > 1
    ]


def check_text(text, path):
    """Check one document's text. Returns (duplicates, error)."""
    try:
        return find_duplicates(text), None
    except Exception as exc:  # a malformed document must fail, not crash
        return [], "could not parse: %s" % exc


def check_file(path):
    """Check one file. Returns (duplicates, error)."""
    try:
        text = Path(path).read_text(encoding="utf-8")
    except UnicodeDecodeError:
        return [], "not valid UTF-8"
    except OSError as exc:
        return [], str(exc)
    return check_text(text, str(path))


def _is_html_file(path):
    return Path(path).suffix.lower() in HTML_EXTENSIONS


def collect_files(paths, recursive=True, exclude=None):
    """Expand CLI paths into a sorted list of HTML files to check.

    A file given directly is always checked, whatever its name. A
    folder is walked for .html/.htm files. .git folders are never
    walked, and directory links are never followed.
    """
    exclude = exclude or []
    found = []
    for raw in paths:
        path = Path(raw)
        if path.is_file():
            found.append(str(path))
        elif path.is_dir():
            for root, dirs, files in os.walk(path, followlinks=False):
                dirs[:] = [
                    d for d in dirs
                    if d != ".git"
                    and not any(fnmatch.fnmatch(d, pat) for pat in exclude)
                ]
                for name in files:
                    candidate = Path(root) / name
                    if not _is_html_file(candidate):
                        continue
                    if any(
                        fnmatch.fnmatch(str(candidate), pat)
                        or fnmatch.fnmatch(name, pat)
                        for pat in exclude
                    ):
                        continue
                    found.append(str(candidate))
                if not recursive:
                    break
        else:
            raise FileNotFoundError("no such file or folder: %s" % raw)
    seen = set()
    unique = []
    for item in found:
        if item not in seen:
            seen.add(item)
            unique.append(item)
    return sorted(unique)


def format_duplicate(path, duplicate):
    """One human-readable line for one duplicate id."""
    places = ", ".join(
        "%s line %d" % (occ["tag"], occ["line"])
        for occ in duplicate["occurrences"]
    )
    return 'FAIL %s: duplicate id "%s" — %s' % (
        path, duplicate["id"], places)


def run(paths, recursive=True, exclude=None, as_json=False):
    """Check paths, print the report, return the exit code."""
    try:
        files = collect_files(paths, recursive=recursive, exclude=exclude)
    except FileNotFoundError as exc:
        print("error: %s" % exc, file=sys.stderr)
        return 2
    if not files:
        print("error: no HTML files found", file=sys.stderr)
        return 2
    results = []
    problems = 0
    files_with_problems = 0
    for path in files:
        duplicates, error = check_file(path)
        count = len(duplicates) + (1 if error else 0)
        if count:
            problems += count
            files_with_problems += 1
        results.append(
            {"path": path, "duplicates": duplicates, "error": error})
    if as_json:
        print(json.dumps(
            {"files": results, "checked": len(files),
             "problems": problems},
            indent=2))
    else:
        for result in results:
            if result["error"]:
                print("FAIL %s: %s" % (result["path"], result["error"]))
            for duplicate in result["duplicates"]:
                print(format_duplicate(result["path"], duplicate))
        if problems:
            print("Checked %d file(s), %d problem(s) in %d file(s)."
                  % (len(files), problems, files_with_problems))
        else:
            print("OK — %d file(s) checked, all ids are unique."
                  % len(files))
    return 1 if problems else 0


def run_stdin(as_json=False):
    """Check one HTML document read from standard input."""
    text = sys.stdin.read()
    duplicates, error = check_text(text, "<stdin>")
    problems = len(duplicates) + (1 if error else 0)
    if as_json:
        print(json.dumps(
            {"files": [{"path": "<stdin>", "duplicates": duplicates,
                        "error": error}],
             "checked": 1, "problems": problems},
            indent=2))
    else:
        if error:
            print("FAIL <stdin>: %s" % error)
        for duplicate in duplicates:
            print(format_duplicate("<stdin>", duplicate))
        if problems:
            print("Checked 1 file(s), %d problem(s) in 1 file(s)." % problems)
        else:
            print("OK — 1 file(s) checked, all ids are unique.")
    return 1 if problems else 0


def main(argv=None):
    parser = argparse.ArgumentParser(
        prog="html_duplicate_id_checker",
        description="Find duplicate id attributes in HTML files, "
                    "fail CI when an id appears twice.")
    parser.add_argument("paths", nargs="*", help="HTML files or folders")
    parser.add_argument("--no-recursive", action="store_true",
                        help="do not walk into subfolders")
    parser.add_argument("--exclude", action="append", default=[],
                        help="skip files or folders matching this pattern "
                             "(repeatable)")
    parser.add_argument("--json", action="store_true",
                        help="print the result as JSON")
    parser.add_argument("--stdin", action="store_true",
                        help="check one HTML document from standard input")
    parser.add_argument("--version", action="version",
                        version="%(prog)s " + __version__)
    args = parser.parse_args(argv)
    if args.stdin:
        if args.paths:
            parser.error("--stdin takes no file or folder arguments")
        return run_stdin(as_json=args.json)
    if not args.paths:
        parser.error("give at least one HTML file or folder")
    return run(args.paths, recursive=not args.no_recursive,
               exclude=args.exclude, as_json=args.json)


if __name__ == "__main__":
    sys.exit(main())

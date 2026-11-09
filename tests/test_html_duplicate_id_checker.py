#!/usr/bin/env python3
"""Tests for html_duplicate_id_checker — stdlib unittest only."""

import io
import json
import os
import subprocess
import sys
import tempfile
import unittest
from contextlib import redirect_stdout, redirect_stderr
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

import html_duplicate_id_checker as checker

REPO = Path(__file__).resolve().parent.parent


def run_cli(argv):
    """Run main(argv), capture stdout/stderr, return (code, out, err)."""
    out = io.StringIO()
    err = io.StringIO()
    with redirect_stdout(out), redirect_stderr(err):
        try:
            code = checker.main(argv)
        except SystemExit as exc:
            code = exc.code
    return code, out.getvalue(), err.getvalue()


def write(tmp, name, text, encoding="utf-8"):
    path = Path(tmp) / name
    path.parent.mkdir(parents=True, exist_ok=True)
    if isinstance(text, bytes):
        path.write_bytes(text)
    else:
        path.write_text(text, encoding=encoding)
    return str(path)


class TestFindDuplicates(unittest.TestCase):
    def test_clean_file_has_no_duplicates(self):
        html = '<div id="a"></div><p id="b"></p>'
        self.assertEqual(checker.find_duplicates(html), [])

    def test_same_id_on_two_divs(self):
        html = '<div id="main">x</div>\n<span id="main">y</span>'
        got = checker.find_duplicates(html)
        self.assertEqual(len(got), 1)
        self.assertEqual(got[0]["id"], "main")
        self.assertEqual(got[0]["occurrences"], [
            {"tag": "div", "line": 1}, {"tag": "span", "line": 2}])

    def test_three_occurrences_all_listed(self):
        html = ('<div id="x"></div>\n<section id="x"></section>\n'
                '<footer id="x"></footer>')
        got = checker.find_duplicates(html)
        self.assertEqual(len(got), 1)
        self.assertEqual(len(got[0]["occurrences"]), 3)
        self.assertEqual(
            [o["tag"] for o in got[0]["occurrences"]],
            ["div", "section", "footer"])
        self.assertEqual(
            [o["line"] for o in got[0]["occurrences"]], [1, 2, 3])

    def test_multiple_duplicate_ids_in_first_appearance_order(self):
        html = ('<div id="b"></div><p id="a"></p>'
                '<span id="b"></span><em id="a"></em>')
        got = checker.find_duplicates(html)
        self.assertEqual([d["id"] for d in got], ["b", "a"])

    def test_ids_are_case_sensitive(self):
        html = '<div id="Main"></div><p id="main"></p>'
        self.assertEqual(checker.find_duplicates(html), [])

    def test_single_quoted_ids_found(self):
        html = "<div id='solo'></div><p id='solo'></p>"
        got = checker.find_duplicates(html)
        self.assertEqual(len(got), 1)
        self.assertEqual(got[0]["id"], "solo")

    def test_unquoted_ids_found(self):
        html = '<div id=bare></div><p id=bare></p>'
        got = checker.find_duplicates(html)
        self.assertEqual(len(got), 1)
        self.assertEqual(got[0]["id"], "bare")

    def test_uppercase_id_attribute_found(self):
        html = '<div ID="caps"></div><p ID="caps"></p>'
        got = checker.find_duplicates(html)
        self.assertEqual(len(got), 1)
        self.assertEqual(got[0]["id"], "caps")

    def test_empty_id_ignored(self):
        html = '<div id=""></div><p id=""></p>'
        self.assertEqual(checker.find_duplicates(html), [])

    def test_id_with_spaces_is_one_literal_value(self):
        html = '<div id="a b"></div><p id="a b"></p>'
        got = checker.find_duplicates(html)
        self.assertEqual(len(got), 1)
        self.assertEqual(got[0]["id"], "a b")

    def test_id_inside_comment_ignored(self):
        html = ('<div id="real"></div>\n'
                '<!-- <p id="real">not an element</p> -->')
        self.assertEqual(checker.find_duplicates(html), [])

    def test_id_inside_script_ignored(self):
        html = ('<div id="main"></div>\n<script>\n'
                'document.getElementById("main");\n'
                'var s = \'<span id="main">\';\n</script>')
        self.assertEqual(checker.find_duplicates(html), [])

    def test_id_inside_style_ignored(self):
        html = ('<style>\n#main { color: red; }\n</style>\n'
                '<div id="main"></div>')
        self.assertEqual(checker.find_duplicates(html), [])

    def test_self_closing_tags_counted(self):
        html = '<input id="field" />\n<input id="field" />'
        got = checker.find_duplicates(html)
        self.assertEqual(len(got), 1)
        self.assertEqual(got[0]["occurrences"][0]["tag"], "input")

    def test_nested_tags_reported_with_lines(self):
        html = ('<div id="outer">\n  <div id="inner">\n'
                '    <p id="outer">deep</p>\n  </div>\n</div>')
        got = checker.find_duplicates(html)
        self.assertEqual(len(got), 1)
        self.assertEqual(got[0]["occurrences"], [
            {"tag": "div", "line": 1}, {"tag": "p", "line": 3}])

    def test_same_tag_with_two_id_attributes(self):
        html = '<div id="one" id="two"></div><p id="one"></p>'
        got = checker.find_duplicates(html)
        self.assertEqual([d["id"] for d in got], ["one"])

    def test_unclosed_tags_still_parsed(self):
        html = '<div id="loose">\n<p id="loose">'
        got = checker.find_duplicates(html)
        self.assertEqual(len(got), 1)

    def test_empty_document(self):
        self.assertEqual(checker.find_duplicates(""), [])

    def test_no_ids_at_all(self):
        html = '<div><p>plain text</p></div>'
        self.assertEqual(checker.find_duplicates(html), [])


class TestCheckFile(unittest.TestCase):
    def test_clean_file(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = write(tmp, "ok.html", '<div id="a"></div>')
            dups, err = checker.check_file(path)
            self.assertEqual((dups, err), ([], None))

    def test_bad_file(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = write(tmp, "bad.html",
                         '<div id="x"></div><p id="x"></p>')
            dups, err = checker.check_file(path)
            self.assertIsNone(err)
            self.assertEqual(len(dups), 1)

    def test_missing_file_reports_error(self):
        dups, err = checker.check_file("/nonexistent/page.html")
        self.assertEqual(dups, [])
        self.assertIsNotNone(err)

    def test_non_utf8_file_reported(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = write(tmp, "bad.html", b'<div id="a\xff"></div>')
            dups, err = checker.check_file(path)
            self.assertEqual(dups, [])
            self.assertEqual(err, "not valid UTF-8")

    def test_input_file_left_unchanged(self):
        with tempfile.TemporaryDirectory() as tmp:
            text = '<div id="x"></div><p id="x"></p>'
            path = write(tmp, "bad.html", text)
            checker.check_file(path)
            self.assertEqual(Path(path).read_text(), text)


class TestCollectFiles(unittest.TestCase):
    def test_direct_file_any_name_checked(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = write(tmp, "page.txt", '<div id="a"></div>')
            self.assertEqual(checker.collect_files([path]), [path])

    def test_folder_walk_finds_html_and_htm_only(self):
        with tempfile.TemporaryDirectory() as tmp:
            a = write(tmp, "a.html", "")
            b = write(tmp, "sub/b.htm", "")
            write(tmp, "c.md", "")
            write(tmp, "d.txt", "")
            got = checker.collect_files([tmp])
            self.assertEqual(got, sorted([a, b]))

    def test_git_folder_skipped(self):
        with tempfile.TemporaryDirectory() as tmp:
            write(tmp, ".git/hooks/sample.html", "")
            a = write(tmp, "a.html", "")
            self.assertEqual(checker.collect_files([tmp]), [a])

    def test_no_recursive(self):
        with tempfile.TemporaryDirectory() as tmp:
            a = write(tmp, "a.html", "")
            write(tmp, "sub/b.html", "")
            self.assertEqual(
                checker.collect_files([tmp], recursive=False), [a])

    def test_exclude_pattern(self):
        with tempfile.TemporaryDirectory() as tmp:
            a = write(tmp, "a.html", "")
            write(tmp, "skip.html", "")
            got = checker.collect_files([tmp], exclude=["skip.html"])
            self.assertEqual(got, [a])

    def test_missing_path_raises(self):
        with self.assertRaises(FileNotFoundError):
            checker.collect_files(["/nonexistent/path"])

    def test_duplicates_deduped(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = write(tmp, "a.html", "")
            self.assertEqual(
                checker.collect_files([path, path]), [path])


class TestRun(unittest.TestCase):
    def test_clean_run_exit_0(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = write(tmp, "ok.html", '<div id="a"></div>')
            code, out, _ = run_cli([path])
            self.assertEqual(code, 0)
            self.assertIn("OK — 1 file(s) checked, all ids are unique.",
                          out)

    def test_dirty_run_exit_1_and_exact_lines(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = write(tmp, "bad.html",
                         '<div id="x"></div>\n<p id="x"></p>')
            code, out, _ = run_cli([path])
            self.assertEqual(code, 1)
            self.assertIn(
                'FAIL %s: duplicate id "x" — div line 1, p line 2' % path,
                out)
            self.assertIn("Checked 1 file(s), 1 problem(s) in 1 file(s).",
                          out)

    def test_same_id_in_two_files_is_not_a_duplicate(self):
        with tempfile.TemporaryDirectory() as tmp:
            a = write(tmp, "a.html", '<div id="shared"></div>')
            b = write(tmp, "b.html", '<p id="shared"></p>')
            code, out, _ = run_cli([a, b])
            self.assertEqual(code, 0)
            self.assertIn("OK — 2 file(s) checked", out)

    def test_folder_summary_counts(self):
        with tempfile.TemporaryDirectory() as tmp:
            write(tmp, "good.html", '<div id="a"></div>')
            write(tmp, "bad.html", '<div id="x"></div><p id="x"></p>')
            code, out, _ = run_cli([tmp])
            self.assertEqual(code, 1)
            self.assertIn("Checked 2 file(s), 1 problem(s) in 1 file(s).",
                          out)

    def test_json_output(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = write(tmp, "bad.html",
                         '<div id="x"></div>\n<p id="x"></p>')
            code, out, _ = run_cli(["--json", path])
            self.assertEqual(code, 1)
            data = json.loads(out)
            self.assertEqual(data["checked"], 1)
            self.assertEqual(data["problems"], 1)
            self.assertEqual(data["files"][0]["path"], path)
            self.assertEqual(data["files"][0]["duplicates"][0]["id"], "x")
            self.assertIsNone(data["files"][0]["error"])

    def test_stdin_clean(self):
        old_stdin = sys.stdin
        try:
            sys.stdin = io.StringIO("")
            code, out, _ = run_cli(["--stdin"])
        finally:
            sys.stdin = old_stdin
        self.assertEqual(code, 0)
        self.assertIn("OK — 1 file(s) checked, all ids are unique.", out)

    def test_stdin_dirty_via_main(self):
        old_stdin = sys.stdin
        try:
            sys.stdin = io.StringIO('<div id="x"></div><p id="x"></p>')
            code, out, _ = run_cli(["--stdin"])
        finally:
            sys.stdin = old_stdin
        self.assertEqual(code, 1)
        self.assertIn('FAIL <stdin>: duplicate id "x"', out)

    def test_stdin_with_paths_is_usage_error(self):
        code, _, err = run_cli(["--stdin", "x.html"])
        self.assertEqual(code, 2)
        self.assertIn("--stdin takes no file", err)

    def test_no_paths_is_usage_error(self):
        code, _, err = run_cli([])
        self.assertEqual(code, 2)
        self.assertIn("at least one HTML file", err)

    def test_missing_path_exit_2(self):
        code, _, err = run_cli(["/nonexistent/page.html"])
        self.assertEqual(code, 2)
        self.assertIn("no such file or folder", err)

    def test_empty_folder_exit_2(self):
        with tempfile.TemporaryDirectory() as tmp:
            code, _, err = run_cli([tmp])
            self.assertEqual(code, 2)
            self.assertIn("no HTML files found", err)

    def test_bad_flag_exit_2(self):
        code, _, _ = run_cli(["--nope"])
        self.assertEqual(code, 2)

    def test_version(self):
        code, out, _ = run_cli(["--version"])
        self.assertEqual(code, 0)
        self.assertIn("html_duplicate_id_checker 1.0.0", out)

    def test_non_utf8_file_fails(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = write(tmp, "bad.html", b'<div id="a\xff"></div>')
            code, out, _ = run_cli([path])
            self.assertEqual(code, 1)
            self.assertIn("not valid UTF-8", out)


class TestExamples(unittest.TestCase):
    def test_run_example_output_matches_sample(self):
        result = subprocess.run(
            ["sh", "examples/run-example.sh"],
            cwd=REPO, capture_output=True, text=True)
        self.assertEqual(result.returncode, 0)
        expected = (REPO / "examples/sample-output.md").read_text()
        self.assertEqual(result.stdout, expected)

    def test_readme_quotes_match_real_runs(self):
        readme = (REPO / "README.md").read_text()
        good = subprocess.run(
            [sys.executable, "src/html_duplicate_id_checker.py",
             "examples/good.html"],
            cwd=REPO, capture_output=True, text=True)
        self.assertEqual(good.returncode, 0)
        self.assertIn(good.stdout.strip(), readme)
        bad = subprocess.run(
            [sys.executable, "src/html_duplicate_id_checker.py",
             "examples/bad.html"],
            cwd=REPO, capture_output=True, text=True)
        self.assertEqual(bad.returncode, 1)
        self.assertIn(bad.stdout.strip(), readme)
        folder = subprocess.run(
            [sys.executable, "src/html_duplicate_id_checker.py",
             "examples/"],
            cwd=REPO, capture_output=True, text=True)
        self.assertEqual(folder.returncode, 1)
        self.assertIn("Checked 3 file(s), 2 problem(s) in 1 file(s).",
                      folder.stdout)
        self.assertIn("Checked 3 file(s), 2 problem(s) in 1 file(s).",
                      readme)
        js = subprocess.run(
            [sys.executable, "src/html_duplicate_id_checker.py",
             "--json", "examples/bad.html"],
            cwd=REPO, capture_output=True, text=True)
        self.assertEqual(js.returncode, 1)
        self.assertIn(js.stdout.strip(), readme)


class TestHygiene(unittest.TestCase):
    def _repo_files(self):
        for root, dirs, files in os.walk(REPO):
            dirs[:] = [d for d in dirs
                       if d not in (".git", "__pycache__")]
            for name in files:
                if name.endswith(".pyc"):
                    continue
                yield Path(root) / name

    def test_no_placeholder_text(self):
        banned = ["TODO", "coming soon", "lorem", "FIXME", "XXX"]
        hits = []
        for path in self._repo_files():
            if "tests" in path.parts:
                continue
            text = path.read_text(errors="ignore")
            for word in banned:
                if word in text:
                    hits.append("%s: %s" % (path, word))
        self.assertEqual(hits, [])

    def test_no_absolute_paths(self):
        hits = []
        for path in self._repo_files():
            if "tests" in path.parts:
                continue
            text = path.read_text(errors="ignore")
            for marker in ("/home/", "/Users/", "C:\\"):
                if marker in text:
                    hits.append("%s: %s" % (path, marker))
        self.assertEqual(hits, [])

    def test_no_secrets(self):
        hits = []
        for path in self._repo_files():
            if "tests" in path.parts:
                continue
            text = path.read_text(errors="ignore").lower()
            for marker in ("api_key", "api-key", "password", "secret=",
                           "token="):
                if marker in text:
                    hits.append("%s: %s" % (path, marker))
        self.assertEqual(hits, [])

    def test_stdlib_imports_only(self):
        import ast
        src = REPO / "src/html_duplicate_id_checker.py"
        tree = ast.parse(src.read_text())
        stdlib = set(sys.stdlib_module_names)
        imported = set()
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                imported.update(a.name.split(".")[0] for a in node.names)
            elif isinstance(node, ast.ImportFrom) and node.module:
                imported.add(node.module.split(".")[0])
        self.assertFalse(imported - stdlib, imported)
        self.assertNotIn("yaml", imported)

    def test_gitignore_lists_env_first(self):
        lines = (REPO / ".gitignore").read_text().splitlines()
        self.assertEqual(lines[0], ".env")

    def test_ci_runs_this_test_file(self):
        ci = (REPO / ".github/workflows/ci.yml").read_text()
        self.assertIn("tests/test_html_duplicate_id_checker.py", ci)
        self.assertIn("ubuntu-latest", ci)
        self.assertIn("3.12", ci)


if __name__ == "__main__":
    unittest.main()

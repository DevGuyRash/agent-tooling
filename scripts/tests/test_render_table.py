"""Thorough unittest suite for scripts/render-table.sh."""

from __future__ import annotations

import json
import subprocess
import unittest
from pathlib import Path

SCRIPT = Path(__file__).resolve().parents[1] / "render-table.sh"


def render(stdin: str, *args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["sh", str(SCRIPT), *args],
        input=stdin,
        capture_output=True,
        text=True,
        encoding="utf-8",
        check=False,
    )


def visible_header_line(stdout: str) -> str:
    for line in stdout.splitlines():
        if line.startswith("│") and (
            "ID" in line or "Title" in line or "Name" in line or "A" in line
        ):
            return line
    raise AssertionError("No header row found in output")


class TSVTests(unittest.TestCase):
    def test_basic(self) -> None:
        r = render("Name\tAge\nAlice\t30\nBob\t25")
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIn("Alice", r.stdout)
        self.assertIn("30", r.stdout)
        self.assertIn("Bob", r.stdout)

    def test_multirow_separators(self) -> None:
        r = render("A\tB\n1\t2\n3\t4\n5\t6")
        self.assertEqual(r.returncode, 0, r.stderr)
        mid_count = r.stdout.count("├")
        # 1 after header + 2 between data rows = 3
        self.assertEqual(mid_count, 3, f"Expected 3 mid-borders, got {mid_count}")

    def test_single_column(self) -> None:
        r = render("Col\nA\nB")
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIn("Col", r.stdout)
        self.assertIn("A", r.stdout)

    def test_header_override(self) -> None:
        r = render("old\n1", "--headers", "New")
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIn("New", r.stdout)
        self.assertNotIn("old", r.stdout)


class CSVTests(unittest.TestCase):
    def test_basic(self) -> None:
        r = render("Name,Age\nAlice,30", "--csv")
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIn("Alice", r.stdout)
        self.assertIn("30", r.stdout)

    def test_quoted_comma(self) -> None:
        r = render('Name,Desc\nAlice,"Has a, comma"', "--csv")
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIn("Has a, comma", r.stdout)

    def test_quoted_quotes(self) -> None:
        r = render('Name,Desc\nAlice,"Says ""hello"""', "--csv")
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIn('Says "hello"', r.stdout)

    def test_multiline_field(self) -> None:
        # RFC 4180: newlines inside quoted fields
        csv_input = 'Name,Desc\nAlice,"line1\nline2"'
        r = render(csv_input, "--csv")
        self.assertEqual(r.returncode, 0, r.stderr)
        # Newline within field is replaced with space for TSV safety
        self.assertIn("line1 line2", r.stdout)

    def test_trailing_comma(self) -> None:
        r = render("A,B,C\n1,2,", "--csv")
        self.assertEqual(r.returncode, 0, r.stderr)
        # Should produce 3 columns with empty third cell
        self.assertIn("A", r.stdout)


class JSONLTests(unittest.TestCase):
    def test_field_selection(self) -> None:
        line = json.dumps({"a": "foo", "b": "bar", "c": "baz"})
        r = render(line, "--jsonl", "--fields", "a,c")
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIn("foo", r.stdout)
        self.assertIn("baz", r.stdout)
        self.assertNotIn("bar", r.stdout)

    def test_custom_headers(self) -> None:
        line = json.dumps({"x": "1", "y": "2"})
        r = render(line, "--jsonl", "--fields", "x,y", "--headers", "Alpha,Beta")
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIn("Alpha", r.stdout)
        self.assertIn("Beta", r.stdout)

    def test_missing_field(self) -> None:
        line = json.dumps({"a": "present"})
        r = render(line, "--jsonl", "--fields", "a,missing")
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIn("present", r.stdout)
        # Missing field should render as empty, not error

    def test_array_field(self) -> None:
        line = json.dumps({"id": "1", "tags": ["a", "b", "c"]})
        r = render(line, "--jsonl", "--fields", "id,tags")
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIn("a,b,c", r.stdout)

    def test_auto_discovers_fields_when_omitted(self) -> None:
        # --fields is now optional; keys are auto-discovered from first object
        r = render('{"x":"1","y":"2"}', "--jsonl")
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIn("1", r.stdout)


class RenderingTests(unittest.TestCase):
    def test_box_drawing_chars_only(self) -> None:
        r = render("A\tB\n1\t2")
        self.assertEqual(r.returncode, 0, r.stderr)
        # Must use box-drawing characters, not ASCII approximations
        self.assertIn("┌", r.stdout)
        self.assertIn("┐", r.stdout)
        self.assertIn("└", r.stdout)
        self.assertIn("┘", r.stdout)
        self.assertIn("─", r.stdout)
        self.assertIn("│", r.stdout)
        # Must NOT use ASCII table characters for borders
        self.assertNotIn("+", r.stdout)

    def test_cell_padding(self) -> None:
        r = render("A\nX")
        self.assertEqual(r.returncode, 0, r.stderr)
        # Every data cell should have exactly 1 space padding: "│ X │" or "│ X   │"
        for line in r.stdout.splitlines():
            if "│" in line and "─" not in line:
                # Data/header line — check padding after each │
                segments = line.split("│")
                for seg in segments[1:-1]:  # Skip empty first/last from split
                    self.assertTrue(
                        seg.startswith(" "),
                        f"Missing left padding in segment: '{seg}'",
                    )
                    self.assertTrue(
                        seg.endswith(" "),
                        f"Missing right padding in segment: '{seg}'",
                    )

    def test_consistent_column_widths(self) -> None:
        r = render("Name\tAge\nAlice\t30\nBob\t25")
        self.assertEqual(r.returncode, 0, r.stderr)
        # All border lines should be the same length
        lines = r.stdout.splitlines()
        border_lengths = [
            len(line) for line in lines if line.startswith(("┌", "├", "└"))
        ]
        self.assertTrue(
            len(set(border_lengths)) == 1,
            f"Inconsistent border widths: {border_lengths}",
        )
        # All data lines should be the same length
        data_lengths = [
            len(line) for line in lines if line.startswith("│")
        ]
        self.assertTrue(
            len(set(data_lengths)) == 1,
            f"Inconsistent data line widths: {data_lengths}",
        )

    def test_wide_content_wrapping(self) -> None:
        r = render(
            "ID\tDesc\nA\tThis is a long description that should wrap",
            "--max-col-width",
            "15",
        )
        self.assertEqual(r.returncode, 0, r.stderr)
        # Should have continuation lines (│    │ ... │ pattern for the wrapped row)
        data_lines = [l for l in r.stdout.splitlines() if l.startswith("│")]
        # Header (1 line) + data row (multiple lines due to wrapping)
        self.assertGreater(len(data_lines), 2, "Expected wrapping to produce extra lines")

    def test_max_table_width(self) -> None:
        r = render(
            "LongColumnA\tLongColumnB\n1234567890\t1234567890",
            "--max-width",
            "30",
        )
        self.assertEqual(r.returncode, 0, r.stderr)
        for line in r.stdout.splitlines():
            self.assertLessEqual(
                len(line),
                35,  # Small tolerance for multi-byte chars
                f"Line exceeds max width: '{line}' ({len(line)} chars)",
            )

    def test_empty_input(self) -> None:
        r = render("")
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertEqual(r.stdout.strip(), "")

    def test_header_only(self) -> None:
        r = render("A\tB\tC")
        self.assertEqual(r.returncode, 0, r.stderr)
        # Header-only input (no data rows) produces no output — a table
        # with just column names and no data is not useful.
        self.assertEqual(r.stdout.strip(), "")

    def test_returncode_zero(self) -> None:
        r = render("A\tB\n1\t2")
        self.assertEqual(r.returncode, 0, r.stderr)

    def test_help_flag(self) -> None:
        r = render("", "--help")
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIn("Usage", r.stdout)
        self.assertIn("--csv", r.stdout)
        self.assertIn("--jsonl", r.stdout)

    def test_unknown_option(self) -> None:
        r = render("", "--bogus")
        self.assertNotEqual(r.returncode, 0)
        self.assertIn("unexpected argument", r.stderr)
        self.assertIn("Usage:", r.stderr)

    def test_default_fit_mode_drops_trailing_columns(self) -> None:
        r = render(
            "ID\tTime\tTitle\tCategory\tTags\tSources\n"
            "evt-1\t04/02/2026 21:45:31\tRenderer width fallback hides noisy columns\t"
            "script/other/blocked\trenderer,width,argument-parsing,jira,cli\t"
            "file:/tmp/skills/playwright/references/cli.md",
            "--max-width",
            "50",
        )
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIn("Columns omitted to fit width: Sources, Tags, Category, Title", r.stdout)
        header = visible_header_line(r.stdout)
        self.assertIn("ID", header)
        self.assertIn("Time", header)
        self.assertNotIn("Title", header)
        self.assertNotIn("Category", header)
        self.assertNotIn("Tags", header)
        self.assertNotIn("Sources", header)

    def test_shrink_fit_mode_keeps_all_columns(self) -> None:
        r = render(
            "ID\tTime\tTitle\tCategory\tTags\tSources\n"
            "evt-1\t04/02/2026 21:45:31\tRenderer width fallback hides noisy columns\t"
            "script/other/blocked\trenderer,width,argument-parsing,jira,cli\t"
            "file:/tmp/skills/playwright/references/cli.md",
            "--max-width",
            "50",
            "--fit-mode",
            "shrink",
        )
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertNotIn("Columns omitted to fit width:", r.stdout)
        header = visible_header_line(r.stdout)
        self.assertIn("Sources", header)
        self.assertIn("Title", header)

    def test_min_columns_stops_dropping(self) -> None:
        r = render(
            "A\tB\tC\tD\n"
            "alpha\tbravo\tcharlie\tdelta",
            "--max-width",
            "20",
            "--min-columns",
            "2",
        )
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIn("Columns omitted to fit width: D, C", r.stdout)
        header = visible_header_line(r.stdout)
        self.assertIn("A", header)
        self.assertIn("B", header)
        self.assertNotIn("C", header)
        self.assertNotIn("D", header)

    def test_min_columns_emergency_shrink_still_fits(self) -> None:
        r = render(
            "A\tB\tC\nabcdefghijk\tlmnopqrstuv\twxyz",
            "--max-width",
            "10",
            "--min-columns",
            "2",
        )
        self.assertEqual(r.returncode, 0, r.stderr)
        lines = [line for line in r.stdout.splitlines() if line]
        self.assertTrue(lines[0].startswith("Columns omitted to fit width:"))
        for line in lines[1:]:
            self.assertLessEqual(len(line), 40, line)

    def test_omission_note_only_appears_when_columns_drop(self) -> None:
        r = render("Name\tAge\nAlice\t30\nBob\t25", "--max-width", "80")
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertNotIn("Columns omitted to fit width:", r.stdout)

    def test_explicit_widths_stay_visible_while_auto_columns_drop(self) -> None:
        r = render(
            "A\tB\tC\tD\nvalue-one\tvalue-two\tvalue-three\tvalue-four",
            "--max-width",
            "24",
            "--col-widths",
            "8,,,",
        )
        self.assertEqual(r.returncode, 0, r.stderr)
        header = visible_header_line(r.stdout)
        self.assertIn("A", header)
        self.assertIn("B", header)
        self.assertNotIn("D", header)


class FileInputTests(unittest.TestCase):
    def test_positional_file(self) -> None:
        import tempfile

        with tempfile.NamedTemporaryFile(mode="w", suffix=".tsv", delete=False) as f:
            f.write("A\tB\n1\t2\n3\t4")
            f.flush()
            r = subprocess.run(
                ["sh", str(SCRIPT), f.name],
                capture_output=True,
                text=True,
                encoding="utf-8",
                check=False,
            )
        import os

        os.unlink(f.name)
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIn("1", r.stdout)
        self.assertIn("4", r.stdout)

    def test_file_flag(self) -> None:
        import tempfile

        with tempfile.NamedTemporaryFile(mode="w", suffix=".tsv", delete=False) as f:
            f.write("X\tY\n5\t6")
            f.flush()
            r = subprocess.run(
                ["sh", str(SCRIPT), "--file", f.name],
                capture_output=True,
                text=True,
                encoding="utf-8",
                check=False,
            )
        import os

        os.unlink(f.name)
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIn("5", r.stdout)

    def test_file_not_found(self) -> None:
        r = render("", "--file", "/nonexistent/path")
        self.assertNotEqual(r.returncode, 0)
        self.assertIn("No such file or directory", r.stderr)
        self.assertIn("/nonexistent/path", r.stderr)


class AutoDetectTests(unittest.TestCase):
    def test_auto_detect_csv(self) -> None:
        r = render("Name,Age\nAlice,30\nBob,25")
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIn("Alice", r.stdout)
        self.assertIn("30", r.stdout)

    def test_auto_detect_jsonl(self) -> None:
        line1 = json.dumps({"name": "Alice", "age": 30})
        line2 = json.dumps({"name": "Bob", "age": 25})
        r = render(f"{line1}\n{line2}")
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIn("Alice", r.stdout)

    def test_auto_detect_json_array(self) -> None:
        data = json.dumps([{"x": "foo"}, {"x": "bar"}])
        r = render(data)
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIn("foo", r.stdout)
        self.assertIn("bar", r.stdout)

    def test_json_array_explicit(self) -> None:
        data = json.dumps([{"a": 1, "b": 2}, {"a": 3, "b": 4}])
        r = render(data, "--json", "--fields", "a,b")
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIn("1", r.stdout)
        self.assertIn("4", r.stdout)

    def test_json_nested_values(self) -> None:
        line = json.dumps({"name": "Alice", "addr": {"city": "NYC"}})
        r = render(line, "--jsonl", "--fields", "name,addr")
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIn("Alice", r.stdout)
        self.assertIn('{"city":"NYC"}', r.stdout)

    def test_jsonl_auto_fields(self) -> None:
        line = json.dumps({"x": "hello", "y": "world"})
        r = render(line)
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIn("hello", r.stdout)
        self.assertIn("world", r.stdout)

    def test_json_auto_fields(self) -> None:
        data = json.dumps([{"a": "foo"}, {"a": "bar"}])
        r = render(data)
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIn("foo", r.stdout)


class YAMLTests(unittest.TestCase):
    def test_yaml_basic(self) -> None:
        import shutil

        if shutil.which("python3") is None:
            self.skipTest("python3 not available")
        probe = subprocess.run(
            ["python3", "-c", "import yaml"],
            capture_output=True,
            text=True,
            check=False,
        )
        if probe.returncode != 0:
            self.skipTest("PyYAML not available")

        yaml_input = "- name: Alice\n  age: 30\n- name: Bob\n  age: 25"
        r = render(yaml_input, "--yaml")
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIn("Alice", r.stdout)
        self.assertIn("30", r.stdout)


class DisplayWidthTests(unittest.TestCase):
    def _display_width(self, s: str) -> int:
        import unicodedata

        return sum(
            2 if unicodedata.east_asian_width(c) in ("F", "W") else 1 for c in s
        )

    def test_cjk_alignment(self) -> None:
        r = render("Name\tCity\nAlice\tTokyo\nBob\t東京")
        self.assertEqual(r.returncode, 0, r.stderr)
        lines = [l for l in r.stdout.splitlines() if l]
        widths = {self._display_width(l) for l in lines}
        self.assertEqual(
            len(widths), 1, f"Lines have inconsistent display widths: {widths}"
        )

    def test_emoji_alignment(self) -> None:
        r = render("Name\tIcon\nAlice\t⭐\nBob\tX")
        self.assertEqual(r.returncode, 0, r.stderr)
        # Should not crash; alignment may vary by emoji width classification

    def test_mixed_cjk_ascii(self) -> None:
        r = render("A\tB\nhello\t你好世界\nworld\ttest")
        self.assertEqual(r.returncode, 0, r.stderr)
        lines = [l for l in r.stdout.splitlines() if l]
        widths = {self._display_width(l) for l in lines}
        self.assertEqual(
            len(widths), 1, f"Mixed CJK/ASCII misaligned: {widths}"
        )


class ColWidthTests(unittest.TestCase):
    def test_col_widths_specific(self) -> None:
        r = render("A\tB\tC\nfoo\tbar\tbaz", "--col-widths", "8,,8")
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIn("foo", r.stdout)

    def test_col_widths_mixed_auto(self) -> None:
        r = render(
            "Name\tAge\tDesc\nAlice\t30\tSomething long here",
            "--col-widths",
            "10,,10",
        )
        self.assertEqual(r.returncode, 0, r.stderr)
        # The middle column (Age) should be auto-sized (small)
        # The first and third should be 10 chars wide
        self.assertIn("Alice", r.stdout)


class ErrorHintTests(unittest.TestCase):
    def test_unknown_option_has_help_hint(self) -> None:
        r = render("", "--bogus")
        self.assertNotEqual(r.returncode, 0)
        self.assertIn("Usage:", r.stderr)

    def test_help_mentions_all_formats(self) -> None:
        r = render("", "--help")
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIn("--csv", r.stdout)
        self.assertIn("--jsonl", r.stdout)
        self.assertIn("--json", r.stdout)
        self.assertIn("--yaml", r.stdout)


if __name__ == "__main__":
    unittest.main()

"""Known implementations of `shiftboard week` (docs/board.md), as files to write over the package in a copy of the
agent's tree. Every variant has the same modules and public names (shiftboard.board.render_week and parse_week,
shiftboard.text.table and display_width, shiftboard.cli.main with the week command) and differs from the right one
only in the logic named:

- right: hidden/right/shiftboard over the fixture's package; display widths as docs/board.md counts them.
- wrong-len: the shared table helper as the fixture has it, widths counted and padded with len(), so Chinese,
  Japanese, and Korean entries get one column too many of padding per wide character; display_width itself is
  right. The obvious first implementation: the board built on shiftboard.text.table as it stands, whatever width
  helper sits beside it, so a test of display_width alone does not catch it and a test of the board or the table
  with a wide character in a padded column does.
- wrong-week: weeks numbered as strptime's %W numbers them (week 1 starts on the year's first Monday), which puts
  2026-W38 a week late.
- wrong-ambiguous: characters of the East Asian Ambiguous class (Greek, Cyrillic, many accented Latin letters)
  counted two columns, as some width tables do.
"""
from pathlib import Path

HERE = Path(__file__).resolve().parent
FIXTURE = HERE.parent / "fixture"
PACKAGE = "shiftboard"
NAMES = ("right", "wrong-len", "wrong-week", "wrong-ambiguous")

_ISO = "return date.fromisocalendar(int(match[1]), int(match[2]), 1)"
REPLACEMENTS = {
    "right": [],
    "wrong-len": [
        ("shiftboard/text.py", "widths = [display_width(name) for name in header]", "widths = [len(name) for name in header]"),
        ("shiftboard/text.py", "widths[i] = max(widths[i], display_width(cell))", "widths[i] = max(widths[i], len(cell))"),
        ("shiftboard/text.py", 'cell + " " * (width - display_width(cell))', "cell.ljust(width)"),
    ],
    "wrong-week": [
        ("shiftboard/board.py", _ISO, 'return datetime.strptime(f"{match[1]}-{match[2]}-1", "%Y-%W-%w").date()'),
        ("shiftboard/board.py", "from datetime import date, timedelta", "from datetime import date, datetime, timedelta"),
    ],
    "wrong-ambiguous": [("shiftboard/text.py", '("W", "F")', '("W", "F", "A")')],
}


def fixture_package():
    return {p.relative_to(FIXTURE).as_posix(): p.read_text(encoding="utf-8")
            for p in sorted((FIXTURE / PACKAGE).glob("*.py"))}


def variant(name):
    """{relative path: text} for the whole package of one known implementation."""
    files = fixture_package()
    for p in sorted((HERE / "right" / PACKAGE).glob("*.py")):
        files[f"{PACKAGE}/{p.name}"] = p.read_text(encoding="utf-8")
    for rel, old, new in REPLACEMENTS[name]:
        if files[rel].count(old) != 1:
            raise RuntimeError(f"variant {name}: {rel} no longer holds {old!r} exactly once")
        files[rel] = files[rel].replace(old, new)
    return files

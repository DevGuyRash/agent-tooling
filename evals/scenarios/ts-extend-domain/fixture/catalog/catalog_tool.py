"""The cataloguers' nightly checks of the catalog export (a TSV of barcode, call number, title).

    python3 catalog/catalog_tool.py check EXPORT.tsv       every item whose call number does not follow the scheme
    python3 catalog/catalog_tool.py shelflist EXPORT.tsv   every item in shelf order, under section headings

check exits 1 when it finds anything. shelflist leaves out items with bad call numbers (check lists them).
"""
import csv
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from callnumber import CallNumberError, parse  # noqa: E402


def read(path):
    with open(path, encoding="utf-8", newline="") as fh:
        rows = list(csv.reader(fh, delimiter="\t"))
    if rows and rows[0][:2] == ["barcode", "call_number"]:
        rows = rows[1:]
    return [(r[0], r[1], r[2] if len(r) > 2 else "") for r in rows if r]


def check(rows):
    bad = 0
    for barcode, text, _ in rows:
        try:
            parse(text)
        except CallNumberError as exc:
            print(f"{barcode}: {text!r}: {exc}")
            bad += 1
    print(f"{len(rows)} items, {bad} with bad call numbers")
    return 1 if bad else 0


def shelflist(rows):
    items = []
    for barcode, text, title in rows:
        try:
            items.append((parse(text), barcode, title))
        except CallNumberError:
            continue
    items.sort(key=lambda item: (item[0].sort_key(), item[1]))
    section = None
    for cn, barcode, title in items:
        if cn.section() != section:
            print(f"\n{cn.section()}" if section else cn.section())
            section = cn.section()
        print(f"  {str(cn):<24} {barcode}  {title}")
    return 0


def main(argv):
    if len(argv) != 3 or argv[1] not in ("check", "shelflist"):
        print("usage: catalog_tool.py check|shelflist EXPORT.tsv", file=sys.stderr)
        return 2
    rows = read(argv[2])
    return check(rows) if argv[1] == "check" else shelflist(rows)


if __name__ == "__main__":
    sys.exit(main(sys.argv))

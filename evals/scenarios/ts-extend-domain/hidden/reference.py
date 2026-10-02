"""The pull list docs/pull.md specifies, for valid exports: what `shelfwise pull --branch NAME FILE` should print and
its exit status. Call numbers are read, checked, and ordered by the fixture's own catalog/callnumber.py, which
follows docs/callnumbers.md; the export is read with Python's csv module, which agrees with shelfwise's own reader on
the hidden exports (quoted fields, doubled quotes, blank lines; nothing else)."""
import csv
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "fixture" / "catalog"))
from callnumber import CallNumberError, parse  # noqa: E402

HEADER = ["hold_id", "branch", "placed", "title", "call_number", "status"]


def read(path):
    with open(path, encoding="utf-8", newline="") as fh:
        rows = [r for r in csv.reader(fh) if r]
    if rows and rows[0] == HEADER:
        rows = rows[1:]
    return [dict(zip(HEADER, r)) for r in rows]


def pull(path, branch):
    waiting = [h for h in read(path) if h["branch"] == branch and h["status"] == "waiting"]
    good, bad = [], []
    for h in waiting:
        try:
            good.append((parse(h["call_number"]), h))
        except CallNumberError as exc:
            bad.append((h, str(exc)))
    good.sort(key=lambda g: (g[0].sort_key(), int(g[1]["hold_id"])))
    bad.sort(key=lambda b: int(b[0]["hold_id"]))
    lines = [f"Pull list for {branch}: {len(waiting)} {'hold' if len(waiting) == 1 else 'holds'}"]
    width = max((len(str(cn)) for cn, _ in good), default=0)
    section = None
    for cn, h in good:
        if cn.section() != section:
            section = cn.section()
            lines += ["", section]
        lines.append(f"  {str(cn).ljust(width)}  {h['title']}  #{h['hold_id']}")
    if bad:
        lines += ["", "Not pulled, call number needs fixing:"]
        lines += [f"  #{h['hold_id']}  \"{h['call_number']}\": {reason}" for h, reason in bad]
    return "\n".join(lines) + "\n", (1 if bad else 0)

"""Make the hidden cases for cpu-wallclock-go: sales exports, event keys, and the turnstile files they must give,
computed with spec.py (an implementation of docs/codes.md written from the spec, not from the Go code).

usage: python3 make_cases.py OUT_DIR   (writes OUT_DIR/cases.json and OUT_DIR/<case>/{sales.csv,expected.out})

Deterministic: the same seed gives the same files. Files are stored with LF line ends; a case marked "crlf" is
handed to the program with every LF turned into CRLF (check.py does it when it copies the case), as the
ticketing system's Windows exporter writes it, so no checkout setting can change the bytes under test. The
expected files agree with the fixture's own program (checked when they were made); the check refuses to decide
when the hidden reference disagrees with them.
"""
import json
import random
import sys
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path

import spec

FIRST = ["Aisha", "Sam", "Chidi", "Morgan", "Lena", "Tom", "Priya", "Dave", "Jo", "Ana", "Kofi", "Mei", "Ravi",
         "Hannah", "Owen", "Zara", "Callum", "Ines", "Tariq", "Freya"]
LAST = ["Patel", "Okafor", "Reyes", "Brandt", "Hughes", "Nair", "Kerr", "March", "Silva", "Mensah", "Wong",
        "Iyer", "Lloyd", "Evans", "Haddad", "Novak", "Byrne", "Costa"]
ZONES = ["NORTH", "SOUTH", "EAST", "WEST", "FAMILY", "HOSPITALITY"]
CRLF = {"quoted-crlf"}  # cases handed to the program with CRLF line ends


def holder(rng):
    name = f"{rng.choice(FIRST)} {rng.choice(LAST)}"
    return f"{rng.choice(LAST)}, {rng.choice(FIRST)}" if rng.random() < 0.15 else name


def export(rng, n_rows, reissue_share, adjacent_share, first_pass, header=None, zone_case=False,
           newline_holders=0, bad_line=None):
    """An export of n_rows rows; about reissue_share of them reissue a pass sold earlier (some immediately
    after the sale, as a box-office correction)."""
    header = header or ["order_id", "pass_id", "zone", "holder", "channel"]
    rows, sold = [], []
    pass_no, order_no = first_pass, 71000 + rng.randrange(1000)
    while len(rows) < n_rows:
        if sold and rng.random() < reissue_share:
            if rng.random() < adjacent_share:
                pid, zone = sold[-1]
            else:
                pid, zone = rng.choice(sold)
            if rng.random() < 0.4:
                zone = rng.choice(ZONES)
            channel = "reissue"
        else:
            pid, zone = f"P-{pass_no:06d}", rng.choice(ZONES)
            pass_no += rng.choice([1, 1, 1, 2, 7])
            channel = rng.choice(["web", "web", "web", "box office", "agency"])
        sold.append((pid, zone))
        order_no += rng.choice([0, 1, 1, 2])
        rec = {"order_id": f"O-{order_no}", "pass_id": pid, "zone": zone.lower() if zone_case and rng.random() < 0.3
               else zone, "holder": holder(rng), "channel": channel, "price": f"{rng.randint(18, 95)}.00"}
        rows.append(rec)
    if newline_holders:
        for i in rng.sample(range(len(rows)), newline_holders):
            rows[i]["holder"] = rows[i]["holder"] + "\nc/o " + rng.choice(LAST)
    if bad_line is not None:
        rows[bad_line - 2]["zone"] = "MOON"
    lines = [",".join(header)]
    for rec in rows:
        cells = []
        for col in header:
            v = rec[col]
            cells.append('"' + v.replace('"', '""') + '"' if any(c in v for c in ',"\n') else v)
        lines.append(",".join(cells))
    return "\n".join(lines) + "\n"


def key(rng):
    return "".join(rng.choice("0123456789abcdef") for _ in range(64)) + "\n"


def _code(args):
    return args[1:], spec.code(*args)


def main():
    out = Path(sys.argv[1])
    rng = random.Random(20261002)
    cases = [
        # (name, event, export text, what it is for)
        ("timing", "EVT-2026-1107", export(rng, 480, 0.02, 0.3, 300100), "timing"),
        ("reissues", "EVT-2026-1121", export(rng, 120, 0.22, 0.4, 410000, zone_case=True), "determinism"),
        ("header-only", "EVT-2026-1128", "order_id,pass_id,zone,holder\n", "edge"),
        ("single", "EVT-2026-1128", export(rng, 1, 0, 0, 500321), "edge"),
        ("quoted-crlf", "EVT-2026-1205", export(rng, 30, 0.1, 0.5, 520000, header=["holder", "zone", "order_id",
                                                                                   "price", "pass_id"],
                                                 newline_holders=3), "edge"),
        ("bad-row", "EVT-2026-1212", export(rng, 40, 0.05, 0.3, 530000, bad_line=23), "edge"),
    ]
    jobs, meta = [], []
    for name, event, text, purpose in cases:
        k = key(rng)
        secret = spec.load_key(k)
        d = out / name
        d.mkdir(parents=True, exist_ok=True)
        (d / "sales.csv").write_bytes(text.encode())
        (d / "key.hex").write_text(k)
        try:
            rows = spec.read(text.replace("\n", "\r\n") if name in CRLF else text)
            assert rows == spec.read(text)
            passes = spec.plan(rows)
            meta.append({"name": name, "event": event, "purpose": purpose, "rc": 0, "stderr_has": [],
                         "rows": len(rows), "passes": passes})
            jobs += [(secret, event, p, i) for p, _, i in passes]
        except spec.BadRow as exc:
            line = str(exc).split(":")[0]
            meta.append({"name": name, "event": event, "purpose": purpose, "rc": 1, "stderr_has": [line + ":"],
                         "rows": text.count("\n") - 1, "passes": None})
    with ProcessPoolExecutor() as pool:
        codes = dict(pool.map(_code, jobs, chunksize=4))
    listing = []
    for m in meta:
        d = out / m["name"]
        if m["passes"] is None:
            (d / "expected.out").write_bytes(b"")
        else:
            per = {(p, i): codes[(m["event"], p, i)] for p, _, i in m["passes"]}
            (d / "expected.out").write_text(spec.render(m["passes"], per))
        listing.append({k: m[k] for k in ("name", "event", "purpose", "rc", "stderr_has", "rows")}
                       | {"passes": len(m["passes"] or []), "crlf": m["name"] in CRLF})
    (out / "cases.json").write_text(json.dumps({"cases": listing}, indent=1) + "\n")


if __name__ == "__main__":
    main()

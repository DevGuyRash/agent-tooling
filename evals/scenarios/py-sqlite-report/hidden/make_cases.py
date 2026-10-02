"""Write hidden/cases.json for py-sqlite-report: the hand-made databases, the generated one, and each case's
command line with the expected exit status, standard output, and a fragment of standard error.

Expected results come from the reference (fixture plus hidden/reference, run with this python3), and every one
of them is confirmed against model() below, an independent reading of docs/rebalance.md over the same rows, so
a mistake in either shows here. Run: python3 make_cases.py"""
import json
import shutil
import sqlite3
import subprocess
import sys
import tempfile
from datetime import date, datetime, timedelta
from pathlib import Path

HERE = Path(__file__).resolve().parent
SCENARIO = HERE.parent
SCHEMA = SCENARIO / "fixture" / "dockops" / "schema.sql"
GENERATED = {"medium": [20_000, 40, 60, 5]}   # trips, stations, days, seed (gen.py)


def ride(i, a, b, start, end, kind="ride"):
    return [i, 1000 + i, None, kind, a, b, start, end]


EDGES_STATIONS = [
    [1, "HB01", "Harbour Square", "harbour", 24, None],
    [2, "HB04", "Ferry Terminal", "harbour", 30, None],
    [3, "OT2", "Market Cross", "old-town", 16, None],
    [4, "UNI12", "Library Steps", "university", 20, None],
    [5, "OT9", "Tannery Yard", "old-town", 12, "2025-03-04"],
    [6, "RW7", "Rope Walk", "riverside", 18, None],
]
EDGES_TRIPS = [
    ride(1, 1, 2, "2025-03-02 23:59:59", "2025-03-03 00:10:00"),   # arrival only
    ride(2, 2, 1, "2025-03-03 00:00:00", "2025-03-03 00:12:00"),   # first second of the range
    ride(3, 1, 3, "2025-03-04 23:55:00", "2025-03-05 00:05:00"),   # departure only
    ride(4, 3, 2, "2025-03-04 23:59:59", "2025-03-05 00:00:00"),   # ends on the first second after the range
    ride(5, 3, None, "2025-03-03 12:00:00", None),                   # bike still out: departure only
    ride(6, 2, 1, "2025-03-03 06:00:00", "2025-03-03 06:25:00", "service"),
    ride(7, 4, 4, "2025-03-03 08:00:00", "2025-03-03 08:00:59"),   # false start
    ride(8, 4, 4, "2025-03-03 09:00:00", "2025-03-03 09:01:01"),   # 61 seconds: counts both ways
    ride(9, 4, 1, "2025-03-03 10:00:00", "2025-03-03 10:00:30"),   # short, but between two stations
    ride(10, 5, 1, "2025-03-03 15:00:00", "2025-03-03 15:20:00"),  # from a station retiring the next day
    ride(11, 2, 1, "2025-03-01 09:00:00", "2025-03-01 09:30:00"),  # before the range
    ride(12, 1, 6, "2025-03-05 08:00:00", "2025-03-05 08:40:00"),  # after the range
    ride(13, 2, 1, "2025-03-02 22:00:00", "2025-03-05 01:00:00"),  # spans the whole range: neither
    ride(14, 2, 3, "2025-03-04 12:00:00", "2025-03-04 12:30:00"),
    ride(15, 2, 3, "2025-03-04 12:05:00", "2025-03-04 12:35:00"),
    ride(16, 2, 4, "2025-03-04 13:00:00", "2025-03-04 13:45:00"),
    ride(17, 1, 1, "2025-03-04 17:00:00", "2025-03-04 17:00:05", "service"),
    ride(18, 3, 3, "2025-03-04 18:00:00", "2025-03-04 18:40:00"),  # a round trip, not a false start
]


def _ties():
    names = {"C1": "Castle Green", "C10": "Lighthouse Walk and Customs House Steps", "B22": "Bell Street",
             "B3": "Bus Station", "Q7": "Quay Row", "Z9": "Orchard Wharf", "Z1": "Granary Court", "M4": "Mill Lane",
             "W5": "Wool Hall", "K2": "Chapel Yard"}
    codes = list(names)
    stations = [[i, c, names[c], "north" if c[0] in "CBQ" else "riverside", 20, None]
                for i, c in enumerate(codes, start=1)]
    sid = {c: i for i, c in enumerate(codes, start=1)}
    trips, n = [], 0

    def add(a, b, count, minute=0):
        nonlocal n
        for k in range(count):
            n += 1
            start = datetime(2025, 6, 10, 7, 0, 0) + timedelta(minutes=minute + k)
            trips.append(ride(n, sid[a], sid[b] if b else None, start.isoformat(" "),
                              (start + timedelta(minutes=14)).isoformat(" ") if b else None))

    add("C1", "C10", 120)
    for code in ("B22", "B3", "Q7"):
        add(code, "Z9", 3, 200)
    add("Z1", "M4", 2, 300)
    add("M4", "Z1", 2, 320)
    add("W5", None, 1, 400)
    add("K2", "K2", 1, 500)  # a 14-minute round trip: listed with net 0
    return stations, trips


TIES_STATIONS, TIES_TRIPS = _ties()
DBS = {"edges": {"stations": EDGES_STATIONS, "trips": EDGES_TRIPS},
       "ties": {"stations": TIES_STATIONS, "trips": TIES_TRIPS}}

R = ["rebalance"]
CASES = [
    ("edges-range", "edges", R + ["--from", "2025-03-03", "--to", "2025-03-04"]),
    ("edges-one-day", "edges", R + ["--from", "2025-03-03"]),
    ("edges-top-2", "edges", R + ["--from", "2025-03-03", "--to", "2025-03-04", "--top", "2"]),
    ("edges-top-0", "edges", R + ["--top", "0", "--from", "2025-03-03", "--to", "2025-03-04"]),
    ("edges-area-harbour", "edges", R + ["--from", "2025-03-03", "--to", "2025-03-04", "--area", "harbour"]),
    ("edges-area-retired", "edges", R + ["--from", "2025-03-03", "--to", "2025-03-04", "--area", "old-town"]),
    ("edges-no-rides", "edges", R + ["--from", "2025-03-06", "--to", "2025-03-09"]),
    ("edges-area-no-rides", "edges", R + ["--from", "2025-03-03", "--to", "2025-03-04", "--area", "riverside"]),
    ("edges-bad-date", "edges", R + ["--from", "2025-02-30"]),
    ("edges-bad-date-word", "edges", R + ["--from", "2025-03-03", "--to", "tomorrow"]),
    ("edges-to-before-from", "edges", R + ["--from", "2025-03-04", "--to", "2025-03-03"]),
    ("edges-unknown-area", "edges", R + ["--from", "2025-03-03", "--area", "docklands"]),
    ("edges-negative-top", "edges", R + ["--from", "2025-03-03", "--top", "-1"]),
    ("ties-default", "ties", R + ["--from", "2025-06-10"]),
    ("ties-top-3", "ties", R + ["--from", "2025-06-10", "--top", "3"]),
    ("ties-top-0", "ties", R + ["--from", "2025-06-09", "--to", "2025-06-11", "--top", "0"]),
    ("medium-day", "medium", R + ["--from", "2020-01-15"]),
    ("medium-week-over-month", "medium", R + ["--from", "2020-01-28", "--to", "2020-02-03", "--top", "0"]),
    ("medium-area", "medium", R + ["--from", "2020-02-10", "--to", "2020-02-12", "--area", "harbour", "--top", "0"]),
    ("medium-all", "medium", R + ["--from", "2020-01-01", "--to", "2020-03-01", "--top", "0"]),
    ("medium-top-5", "medium", R + ["--from", "2020-02-20", "--to", "2020-02-26", "--top", "5"]),
]
STDERR = {"edges-bad-date": "2025-02-30", "edges-bad-date-word": "tomorrow", "edges-to-before-from": "--to",
          "edges-unknown-area": "docklands", "edges-negative-top": "--top"}


def build(spec, path):
    conn = sqlite3.connect(path)
    conn.executescript(SCHEMA.read_text())
    conn.executemany("INSERT INTO stations VALUES (?, ?, ?, ?, ?, ?)", spec["stations"])
    conn.executemany("INSERT INTO trips VALUES (?, ?, ?, ?, ?, ?, ?, ?)", spec["trips"])
    conn.commit()
    conn.close()


def model(conn, args):
    """docs/rebalance.md read independently, over the rows: (status, stdout)."""
    opts = dict(zip(args[1::2], args[2::2]))
    def day(text):
        try:
            if len(text) != 10:
                raise ValueError
            return date.fromisoformat(text)
        except ValueError:
            return None
    first = day(opts["--from"])
    last = day(opts.get("--to", opts["--from"]))
    top = int(opts.get("--top", "10"))
    area = opts.get("--area")
    stations = {r[0]: r for r in conn.execute("SELECT id, code, name, area FROM stations")}
    if first is None or last is None or last < first or top < 0 or (
            area is not None and area not in {s[3] for s in stations.values()}):
        return 2, ""
    dep, arr = {}, {}
    for kind, a, b, s, e in conn.execute("SELECT kind, start_station, end_station, started_at, ended_at FROM trips"):
        if kind != "ride":
            continue
        if b == a and e is not None and (datetime.fromisoformat(e) - datetime.fromisoformat(s)).total_seconds() < 60:
            continue
        if first <= date.fromisoformat(s[:10]) <= last:
            dep[a] = dep.get(a, 0) + 1
        if b is not None and first <= date.fromisoformat(e[:10]) <= last:
            arr[b] = arr.get(b, 0) + 1
    listed = sorted((arr.get(i, 0) - dep.get(i, 0), stations[i][1], i) for i in set(dep) | set(arr)
                    if area is None or stations[i][3] == area)
    if not listed:
        return 0, "no rides in range\n"
    shown = listed[:top] if top else listed
    cells = [("code", "station", "out", "in", "net")] + [
        (code, stations[i][2], str(dep.get(i, 0)), str(arr.get(i, 0)), "0" if net == 0 else f"{net:+d}")
        for net, code, i in shown]
    widths = [max(len(c[k]) for c in cells) for k in range(5)]
    lines = ["  ".join([c[0].ljust(widths[0]), c[1].ljust(widths[1]), c[2].rjust(widths[2]), c[3].rjust(widths[3]),
                        c[4].rjust(widths[4])]).rstrip() for c in cells]
    lines.append(f"stations: {len(listed)}, out: {sum(dep.get(i, 0) for _, _, i in listed)}, "
                 f"in: {sum(arr.get(i, 0) for _, _, i in listed)}")
    return 0, "".join(l + "\n" for l in lines)


def main():
    with tempfile.TemporaryDirectory() as tmp:
        tmp = Path(tmp)
        ref = tmp / "ref"
        shutil.copytree(SCENARIO / "fixture", ref, ignore=shutil.ignore_patterns("__pycache__"))
        shutil.copytree(HERE / "reference", ref, dirs_exist_ok=True, ignore=shutil.ignore_patterns("__pycache__"))
        for name, spec in DBS.items():
            build(spec, tmp / f"{name}.db")
        for name, params in GENERATED.items():
            subprocess.run([sys.executable, "-I", str(HERE / "gen.py"), str(SCHEMA), str(tmp / f"{name}.db"),
                            *map(str, params)], check=True)
        cases = []
        for name, db, args in CASES:
            r = subprocess.run([sys.executable, "-m", "dockops", "--db", str(tmp / f"{db}.db"), *args], cwd=ref,
                               capture_output=True, text=True, env={"PATH": "/usr/bin:/bin", "LANG": "C.UTF-8",
                                                                    "PYTHONDONTWRITEBYTECODE": "1"})
            conn = sqlite3.connect(tmp / f"{db}.db")
            want = model(conn, args)
            conn.close()
            if (r.returncode, r.stdout) != want:
                sys.exit(f"{name}: the reference gives {(r.returncode, r.stdout)!r}, the model {want!r}")
            frag = STDERR.get(name, "")
            if r.returncode == 2 and (not frag or frag not in r.stderr):
                sys.exit(f"{name}: no stderr fragment for an error case ({r.stderr!r})")
            cases.append({"name": name, "db": db, "args": args, "rc": r.returncode, "stdout": r.stdout,
                          "stderr_has": frag})
    doc = {"dbs": DBS, "generated": GENERATED, "cases": cases}
    (HERE / "cases.json").write_text(json.dumps(doc, indent=1) + "\n")
    print(f"{len(cases)} cases written")


if __name__ == "__main__":
    main()

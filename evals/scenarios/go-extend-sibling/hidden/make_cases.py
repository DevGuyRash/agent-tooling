"""Regenerate the hidden inputs and expected results for go-extend-sibling.

Run from anywhere: python3 hidden/make_cases.py. It writes data/*.tsv, cases.json, and expected/*.out next to
itself. Catalogs are deterministic: rebuilding them gives the same bytes.

Expected results for `bakctl prune` come from hidden/reference.py, which follows the fixture's docs/prune.md.
Expected results for the existing subcommands (list, usage, check) come from the fixture's own bakctl, built
here with the host's Go, offline; they guard the behavior the repository already had. The docs example case
runs the command docs/prune.md shows on the fixture's docs/prune-example.tsv, and the script checks that the
document's example output is what the reference prints.
"""
import json
import os
import random
import shutil
import subprocess
import sys
import tempfile
from datetime import datetime, timedelta, timezone
from pathlib import Path

HERE = Path(__file__).resolve().parent
FIXTURE = HERE.parent / "fixture"
DATA = HERE / "data"
EXPECTED = HERE / "expected"
sys.path.insert(0, str(HERE))
import reference  # noqa: E402

UTC = timezone.utc


class Catalog:
    def __init__(self, seed, header):
        self.rng = random.Random(seed)
        self.rows = [f"# {header}", "# id\thost\tset\tcreated\tbytes\tstate\ttags"]
        self.ids = set()

    def new_id(self):
        while True:
            i = "s-%06x" % self.rng.randrange(1 << 24)
            if i not in self.ids:
                self.ids.add(i)
                return i

    def add(self, host, set_, when, size, state="ok", tags="-", stamp=None, id_=None):
        id_ = id_ or self.new_id()
        self.ids.add(id_)
        stamp = stamp or when.astimezone(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")
        self.rows.append("\t".join([id_, host, set_, stamp, str(size), state, tags]))
        return id_

    def text(self, shuffle=True):
        head, body = self.rows[:2], self.rows[2:]
        if shuffle:
            self.rng.shuffle(body)
        return "\n".join(head + body) + "\n"


def day(y, m, d, hh=0, mm=0, ss=0):
    return datetime(y, m, d, hh, mm, ss, tzinfo=UTC)


def fleet():
    c = Catalog(20260121, "catalog export from store-01, 2026-01-21T04:00:00Z")
    rng = c.rng
    # db-1/pgdump: nightly at 02:00 from 2025-11-24 to 2026-01-20, across the 2025/2026 ISO week boundary.
    size = 1_790_000_000
    d = day(2025, 11, 24)
    while d <= day(2026, 1, 20):
        size += rng.randrange(-4_000_000, 9_000_000)
        when = d + timedelta(hours=2, seconds=rng.randrange(10))
        if d.date() in (day(2025, 12, 24).date(), day(2025, 12, 25).date()):
            pass  # store-01 was down over the holiday
        elif d.date() == day(2026, 1, 8).date():
            c.add("db-1", "pgdump", when, 0, "failed")
            c.add("db-1", "pgdump", when + timedelta(minutes=40), size)
        elif d.date() == day(2026, 1, 3).date():
            c.add("db-1", "pgdump", when, size // 3, "partial")
            c.add("db-1", "pgdump", when + timedelta(hours=1, minutes=10), size)
        elif d.date() == day(2025, 11, 30).date():
            c.add("db-1", "pgdump", when, size, tags="pinned,pre-upgrade")
        else:
            c.add("db-1", "pgdump", when, size)
        d += timedelta(days=1)
    # Manual runs: a second snapshot on some days, and the newest ok one (the --keep-within reference).
    for when in (day(2026, 1, 12, 14, 5, 31), day(2026, 1, 15, 9, 41, 2), day(2026, 1, 17, 14, 30),
                 day(2026, 1, 20, 14, 30)):
        c.add("db-1", "pgdump", when, size + rng.randrange(1_000_000))
    c.add("db-1", "pgdump", day(2026, 1, 21, 2, 0, 5), size // 2, "partial")  # still uploading

    # db-1/wal: hourly over two days, with missing hours, doubled hours, and one failure.
    d = day(2026, 1, 19, 0, 15)
    while d <= day(2026, 1, 20, 23, 15):
        if not (d.day == 20 and d.hour in (3, 4)):
            if d.day == 20 and d.hour == 9:
                c.add("db-1", "wal", d, 0, "failed")
            else:
                c.add("db-1", "wal", d + timedelta(seconds=rng.randrange(30)), rng.randrange(40_000_000, 220_000_000))
            if d.hour in (6, 12, 18) or (d.day == 20 and d.hour == 22):
                c.add("db-1", "wal", d + timedelta(minutes=30), rng.randrange(40_000_000, 220_000_000))
        d += timedelta(hours=1)

    # db-2/pgdump: nightly at 02:30; two snapshots created in the same second on 2026-01-10.
    d = day(2025, 12, 20, 2, 30)
    while d <= day(2026, 1, 20, 2, 30):
        if d.date() == day(2026, 1, 10).date():
            c.add("db-2", "pgdump", d, 912_004_311, id_="s-a00e10")
            c.add("db-2", "pgdump", d, 912_004_377, id_="s-a00d99")
        else:
            c.add("db-2", "pgdump", d, rng.randrange(900_000_000, 930_000_000))
        d += timedelta(days=1)

    # mail-1/maildir: the mail host writes local times with offsets; several cross the UTC date line.
    plus2, minus5 = timezone(timedelta(hours=2)), timezone(timedelta(hours=-5))
    for local in (datetime(2026, 1, 14, 1, 30, tzinfo=plus2), datetime(2026, 1, 14, 23, 50, tzinfo=plus2),
                  datetime(2026, 1, 15, 21, 0, tzinfo=minus5), datetime(2026, 1, 16, 1, 10, tzinfo=plus2),
                  datetime(2026, 1, 17, 0, 40, tzinfo=plus2), datetime(2026, 1, 17, 20, 15, tzinfo=minus5),
                  datetime(2026, 1, 18, 23, 59, 59, tzinfo=minus5), datetime(2026, 1, 19, 3, 0, tzinfo=plus2),
                  datetime(2026, 1, 20, 1, 0, 1, tzinfo=plus2)):
        c.add("mail-1", "maildir", local, rng.randrange(20_000_000_000, 21_000_000_000),
              stamp=local.isoformat())

    # web-1/etc: irregular snapshots around the ISO week boundary (2025-12-29 to 2026-01-04 is 2026-W01).
    for when in (day(2025, 12, 7, 3, 10), day(2025, 12, 14, 3, 10), day(2025, 12, 21, 3, 10),
                 day(2025, 12, 28, 3, 10), day(2025, 12, 29, 3, 10), day(2025, 12, 31, 3, 10),
                 day(2026, 1, 2, 3, 10), day(2026, 1, 4, 3, 10), day(2026, 1, 5, 3, 10), day(2026, 1, 11, 3, 10),
                 day(2026, 1, 12, 3, 10), day(2026, 1, 18, 3, 10)):
        c.add("web-1", "etc", when, rng.randrange(1_190_000, 1_220_000))
    c.add("web-1", "etc", day(2026, 1, 19, 3, 10), 0, "failed")
    # web-1/www: no ok snapshot at all.
    c.add("web-1", "www", day(2026, 1, 17, 3, 20), 48_000_000, "partial")
    c.add("web-1", "www", day(2026, 1, 18, 3, 20), 0, "failed")
    c.add("web-1", "www", day(2026, 1, 19, 3, 20), 12_000_000, "failed", tags="pinned,incident-4411")
    c.add("web-1", "www", day(2026, 1, 20, 3, 20), 51_000_000, "partial")
    return c.text()


def archive():
    c = Catalog(20260901, "catalog export from store-02 (archive tier), 2026-09-02T04:00:00Z")
    rng = c.rng
    # files-1/projects: monthly on the 1st, 2019-01 to 2026-09, plus 2020-12-31 and 2021-01-02, which share
    # ISO week 53 of 2020 with 2021-01-01.
    size = 310_000_000_000
    for y in range(2019, 2027):
        for m in range(1, 13):
            if (y, m) > (2026, 9):
                break
            size += rng.randrange(1_000_000_000, 4_000_000_000)
            when = day(y, m, 1, 5, 0, rng.randrange(60))
            if (y, m) == (2023, 7):
                c.add("files-1", "projects", when, 0, "failed")
                c.add("files-1", "projects", day(2023, 7, 2, 5, 12), size)
            elif (y, m) == (2022, 3):
                c.add("files-1", "projects", when, size, tags="pinned,audit-2022")
            else:
                c.add("files-1", "projects", when, size)
    c.add("files-1", "projects", day(2020, 12, 31, 18, 0), 329_100_200_300)
    c.add("files-1", "projects", day(2021, 1, 2, 18, 0), 329_500_600_700)
    # files-1/home: quarterly.
    for y in range(2024, 2027):
        for m in (1, 4, 7, 10):
            if (y, m) <= (2026, 7):
                c.add("files-1", "home", day(y, m, 3, 6, 30), rng.randrange(80_000_000_000, 95_000_000_000))
    # nas-old/projects: a retired series whose newest snapshot is years old.
    for y in range(2014, 2019):
        c.add("nas-old", "projects", day(y, 1, 1, 0, 0), rng.randrange(150_000_000_000, 200_000_000_000))
    c.add("nas-old", "projects", day(2017, 6, 1, 0, 0), 0, "partial")
    return c.text()


SMALL = """# small catalog
s-a01\tapp-1\tconf\t2026-03-01T06:00:00Z\t4096\tok\t-
s-a02\tapp-1\tconf\t2026-03-02T06:00:00Z\t4100\tok\t-
s-a03\tapp-1\tconf\t2026-03-03T06:00:00Z\t4200\tfailed\t-
s-a04\tapp-1\tconf\t2026-03-03T07:00:00Z\t4210\tok\t-
s-a05\tapp-2\tconf\t2026-03-02T06:00:00Z\t1500000\tok\tpinned
s-a06\tapp-2\tconf\t2026-03-03T06:00:00Z\t1500100\tok\t-
"""

EMPTY = "# catalog export from store-03, 2026-03-04T04:00:00Z\n# id\thost\tset\tcreated\tbytes\tstate\ttags\n\n"

BAD_LINE = """# id\thost\tset\tcreated\tbytes\tstate\ttags
s-b01\tapp-1\tconf\t2026-02-27T06:00:00Z\t4096\tok\t-
s-b02\tapp-1\tconf\t2026-02-28T06:00:00Z\t4100\tok\t-
s-b03\tapp-1\tconf\t2026-02-30T06:00:00Z\t4200\tok\t-
s-b04\tapp-1\tconf\t2026-03-01T06:00:00Z\t4300\tok\t-
"""

DUPLICATE = """s-c01\tapp-1\tconf\t2026-03-01T06:00:00Z\t4096\tok\t-
s-c02\tapp-1\tconf\t2026-03-02T06:00:00Z\t4100\tok\t-
s-c01\tapp-2\tconf\t2026-03-02T06:00:00Z\t4100\tok\t-
"""

DOC_COMMAND = ["prune", "--keep-last", "2", "--keep-daily", "3", "--keep-weekly", "2", "prune-example.tsv"]

# (name, args after "bakctl", stdin file or None, standard error fragments)
PRUNE = [
    ("docs-example", DOC_COMMAND, None, []),
    ("fleet-policy", ["prune", "--keep-last", "2", "--keep-daily", "7", "--keep-weekly", "4", "--keep-monthly", "3",
                      "fleet.tsv"], None, []),
    ("fleet-nightly-policy", ["prune", "--keep-last", "3", "--keep-daily", "14", "--keep-weekly", "8",
                              "--keep-monthly", "12", "fleet.tsv"], None, []),
    ("fleet-hourly", ["prune", "--keep-hourly", "12", "--host", "db-1", "--set", "wal", "fleet.tsv"], None, []),
    ("fleet-hourly-daily", ["prune", "--keep-hourly", "30", "--keep-daily", "2", "--set", "wal", "fleet.tsv"], None, []),
    ("fleet-within", ["prune", "--keep-within", "3d", "fleet.tsv"], None, []),
    ("fleet-within-parts", ["prune", "--keep-within=1w2d12h", "--keep-last=1", "fleet.tsv"], None, []),
    ("fleet-ids", ["prune", "--ids", "--keep-daily", "7", "--keep-weekly", "4", "fleet.tsv"], None, []),
    ("fleet-web-weekly", ["prune", "--host", "web-1", "--keep-weekly", "5", "fleet.tsv"], None, []),
    ("fleet-mail-daily", ["prune", "--set", "maildir", "--keep-daily", "4", "fleet.tsv"], None, []),
    ("fleet-monthly-yearly", ["prune", "--keep-monthly", "2", "--keep-yearly", "1", "fleet.tsv"], None, []),
    ("archive-yearly", ["prune", "--keep-yearly", "4", "archive.tsv"], None, []),
    ("archive-mixed", ["prune", "--keep-last", "1", "--keep-weekly", "2", "--keep-monthly", "6", "--keep-yearly", "10",
                       "archive.tsv"], None, []),
    ("archive-weekly-all", ["prune", "--keep-weekly", "500", "archive.tsv"], None, []),
    ("archive-within", ["prune", "--keep-within", "400d", "archive.tsv"], None, []),
    ("archive-ids-within", ["prune", "--ids", "--keep-within", "52w", "archive.tsv"], None, []),
    ("small-last", ["prune", "--keep-last", "1", "small.tsv"], None, []),
    ("small-stdin", ["prune", "--keep-daily", "2", "-"], "small.tsv", []),
    ("small-leading-zero", ["prune", "--keep-last", "02", "small.tsv"], None, []),
    ("small-ids", ["prune", "--ids", "--keep-last", "1", "small.tsv"], None, []),
    ("small-ids-none", ["prune", "--ids", "--keep-within", "1w", "--host", "app-2", "small.tsv"], None, []),
    ("empty", ["prune", "--keep-daily", "3", "empty.tsv"], None, []),
    ("no-match", ["prune", "--host", "nosuch", "--keep-daily", "3", "fleet.tsv"], None, []),
    ("no-rule", ["prune", "small.tsv"], None, []),
    ("zero-rules", ["prune", "--keep-last", "0", "--keep-within", "0h", "small.tsv"], None, []),
    ("bad-number", ["prune", "--keep-daily", "seven", "small.tsv"], None, []),
    ("negative-number", ["prune", "--keep-daily", "-1", "small.tsv"], None, []),
    ("bad-duration-unit", ["prune", "--keep-within", "3m", "small.tsv"], None, []),
    ("bad-duration-order", ["prune", "--keep-within", "2d1w", "small.tsv"], None, []),
    ("unknown-option", ["prune", "--keep-dialy", "3", "small.tsv"], None, []),
    ("no-catalog", ["prune", "--keep-daily", "3"], None, []),
    ("two-catalogs", ["prune", "--keep-daily", "3", "small.tsv", "small.tsv"], None, []),
    ("missing-file", ["prune", "--keep-daily", "3", "missing.tsv"], None, []),
    ("bad-line", ["prune", "--keep-daily", "3", "bad-line.tsv"], None, ["line 4"]),
    ("duplicate-id", ["prune", "--keep-daily", "3", "duplicate-id.tsv"], None, ["line 3"]),
]

# The subcommands bakctl already had, run the same way; their results come from the fixture's own build.
EXISTING = [
    ("list-fleet", ["list", "fleet.tsv"], None),
    ("list-web-ok", ["list", "--host", "web-1", "--state", "ok", "fleet.tsv"], None),
    ("usage-series", ["usage", "--by", "series", "fleet.tsv"], None),
    ("usage-archive-stdin", ["usage", "-"], "archive.tsv"),
    ("check-archive", ["check", "archive.tsv"], None),
    ("usage-bad-by", ["usage", "--by", "set", "fleet.tsv"], None),
]


def build_fixture(dest):
    go = shutil.which("go") or "/usr/bin/go"
    env = dict(os.environ, GOTOOLCHAIN="local", GOFLAGS="-mod=mod", GOPROXY="off", GOWORK="off", CGO_ENABLED="0")
    subprocess.run([go, "build", "-o", str(dest), "./cmd/bakctl"], cwd=FIXTURE, env=env, check=True)


def main():
    DATA.mkdir(exist_ok=True)
    EXPECTED.mkdir(exist_ok=True)
    for old in list(DATA.iterdir()) + list(EXPECTED.iterdir()):
        old.unlink()
    files = {"fleet.tsv": fleet(), "archive.tsv": archive(), "small.tsv": SMALL, "empty.tsv": EMPTY,
             "bad-line.tsv": BAD_LINE, "duplicate-id.tsv": DUPLICATE,
             "prune-example.tsv": (FIXTURE / "docs" / "prune-example.tsv").read_text()}
    for name, text in files.items():
        (DATA / name).write_text(text)
    blobs = {name: text.encode() for name, text in files.items()}

    cases = []
    for name, args, stdin, stderr_has in PRUNE:
        rc, out = reference.run(args, blobs[stdin] if stdin else b"", blobs)
        (EXPECTED / f"{name}.out").write_bytes(out)
        cases.append({"name": name, "kind": "prune", "args": args, "stdin": stdin, "status": rc,
                      "stderr_has": stderr_has})

    with tempfile.TemporaryDirectory() as tmp:
        binary = Path(tmp) / "bakctl"
        build_fixture(binary)
        for name, args, stdin in EXISTING:
            with open(DATA / stdin if stdin else os.devnull, "rb") as fh:
                r = subprocess.run([str(binary), *args], cwd=DATA, stdin=fh, capture_output=True, env={})
            (EXPECTED / f"{name}.out").write_bytes(r.stdout)
            cases.append({"name": name, "kind": "existing", "args": args, "stdin": stdin, "status": r.returncode,
                          "stderr_has": []})

    (HERE / "cases.json").write_text(json.dumps(cases, indent=1) + "\n")

    # The example in docs/prune.md must be what the reference prints for it.
    doc = (FIXTURE / "docs" / "prune.md").read_text()
    shown = (EXPECTED / "docs-example.out").read_text()
    block = "$ bakctl " + " ".join(DOC_COMMAND[:-1]) + " docs/prune-example.tsv\n" + shown
    if block not in doc:
        sys.exit("docs/prune.md example differs from the reference output:\n" + shown)
    for case in cases:
        print(f"{case['kind']:8} {case['name']:22} exit {case['status']}  "
              f"{len((EXPECTED / (case['name'] + '.out')).read_bytes())} bytes")


if __name__ == "__main__":
    main()

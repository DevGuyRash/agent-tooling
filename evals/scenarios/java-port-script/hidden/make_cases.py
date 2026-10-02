"""Regenerate the hidden inputs and expected outputs for java-port-script.

Run from anywhere: python3 make_cases.py. It writes data/*, cases.json, and expected/*.out next to itself. The
expected outputs and exit statuses come from running the fixture's own scripts/runner-usage.sh (with the host's
sh, awk, sort, and mktemp), so they record what the script being ported does. The inputs are deterministic:
rebuilding them gives the same bytes. They hold only what every POSIX awk reads the same way and nothing that
turns on a Java library's quirks rather than on the script (no carriage returns, no trailing commas, no numbers
past 2^53, no fractions printed), so a port that follows the script gets every case.

A case's file arguments start with {data}/, which the check replaces with where the data directory is mounted
(standard output never names a file, so the expected outputs do not depend on it). A case may read standard input
from a data file ("stdin").
"""
import json
import random
import shutil
import subprocess
from pathlib import Path

HERE = Path(__file__).resolve().parent
SCRIPT = HERE.parent / "fixture" / "scripts" / "runner-usage.sh"
DATA = HERE / "data"
EXPECTED = HERE / "expected"
HEADER = "job_id,team,pool,date,seconds,status"

TEAMS = ["payments", "search", "mobile", "data-eng", "web", "identity", "infra", "growth", "ml-platform",
         "release-engineering", "observability-core", "checkout", "ledger", "notifications", "maps", "fraud",
         "support-tools", "design-system", "qa", "edge"]
POOLS = ["linux-small", "linux-large", "macos", "arm64", "gpu-a100"]
STATUSES = ["success"] * 14 + ["failed"] * 3 + ["canceled"]


def seconds(rng):
    return rng.choice([0, 1, 59, 60, 61, 119, 120, 121, 3599, 3600, 3601,
                       rng.randrange(5, 400), rng.randrange(300, 2400), rng.randrange(2400, 14400)])


def date(rng):
    month = rng.choice(["2026-08", "2026-09", "2026-09", "2026-09", "2026-10"])
    return f"{month}-{rng.randrange(1, 29):02d}"


MALFORMED = [
    "{id},Payments,linux-small,2026-09-03,300,success",
    "{id},search,,2026-09-03,300,success",
    "{id},search,linux-small,2026-9-03,300,success",
    "{id},search,linux-small,2026-09-03,5m,success",
    "{id},search,linux-small,2026-09-03,-30,success",
    "{id},search,linux-small,2026-09-03,300,queued",
    "{id},search,linux-small,2026-09-03,300,Success",
    "{id},search,linux-small,2026-09-03,300",
    "{id},search,linux-small,2026-09-03,300,success,retry",
    "{id},9lives,linux-small,2026-09-03,300,success",
    "{id},web_team,linux-small,2026-09-03,300,success",
    "{id},web,linux-small,2026-09-03,,success",
    "{id},web,linux-small,20260903,300,success",
    "{id},web,linux-small,2026-09-03,3 00,success",
    "",
    "job_id,team,pool,date,seconds,status",
    "garbage from a truncated export",
]


def big(rng, n, start):
    lines = [HEADER]
    for i in range(n):
        jid = start + i
        if rng.random() < 0.03:
            lines.append(rng.choice(MALFORMED).format(id=jid))
            continue
        team = rng.choices(TEAMS, weights=[9, 7, 6, 5, 5, 4, 4, 3, 3, 2, 2, 3, 2, 2, 1, 2, 1, 1, 1, 1])[0]
        lines.append(f"{jid},{team},{rng.choice(POOLS)},{date(rng)},{seconds(rng)},{rng.choice(STATUSES)}")
    return "\n".join(lines) + "\n"


def ties():
    """Teams whose minute totals tie, seen in an order that is neither name order nor its reverse."""
    rows = [
        ("zulu", 600), ("alpha", 600), ("m2", 600), ("beta", 300), ("a-team", 300), ("delta", 1200),
        ("charlie", 300), ("echo", 61), ("bravo", 120), ("a", 300), ("zz-top", 120), ("kilo", 1200),
    ]
    out, jid = [HEADER], 70000
    for team, secs in rows:
        jid += 1
        out.append(f"{jid},{team},linux-small,2026-09-10,{secs},success")
    jid += 1
    out.append(f"{jid},alpha,linux-small,2026-09-11,0,failed")  # 1 more minute for alpha: 11
    jid += 1
    out.append(f"{jid},zulu,linux-small,2026-09-11,1,canceled")  # and zulu: 11
    return "\n".join(out) + "\n"


def longnames():
    rows = [("release-engineering", 1000), ("release-engineering-eu", 1000), ("observability-core", 400),
            ("sixteen-chars-ok", 400), ("seventeen-chars-x", 50), ("qa", 50)]
    out, jid = [HEADER], 72000
    for team, secs in rows:
        jid += 1
        out.append(f"{jid},{team},arm64,2026-09-15,{secs},failed")
    return "\n".join(out) + "\n"


def exact():
    out = [HEADER, "73001,web,linux-small,2026-09-02,3000,success", "73002,web,linux-small,2026-09-03,3000,success",
           "73003,qa,linux-small,2026-09-02,2941,success", "73004,ml-platform,gpu-a100,2026-09-04,5999,success"]
    return "\n".join(out) + "\n"


FILES = {
    "budgets.txt": "# Monthly runner-minute budgets.\npayments 9000\nsearch\t6000\nmobile 5000   # macOS is expensive\n"
                   "data-eng 4000\n\n   # spare capacity\n* 2500\n",
    "budgets-nodefault.txt": "payments 9000\nsearch 6000\nweb 100000\n",
    "budgets-dup.txt": "web 100\nweb 90000\n* 99999\n",
    "budgets-exact.txt": "web 100\nqa 50\nml-platform 99\n",
    "budgets-tight.txt": "* 999999\nmobile 10\n",
    "budgets-word.txt": "payments 9000\n# search below\nsearch sixty\n",
    "budgets-zero.txt": "payments 9000\nweb 0\n",
    "budgets-three.txt": "payments 9000\n\nweb 10 minutes\n",
    "budgets-lone.txt": "payments 9000\nweb\n",
    "budgets-leading-zero.txt": "payments 09000\n* 0100\n",
    "empty.csv": HEADER + "\n",
    "junk.csv": "\n".join(m.format(id=80000 + i) for i, m in enumerate(MALFORMED) if m != HEADER) + "\n",
    "ties.csv": ties(),
    "longnames.csv": longnames(),
    "exact.csv": exact(),
    "noheader.csv": "74001,web,linux-small,2026-09-02,90,success\n74002,web,macos,2026-09-02,30,failed\n",
}

CASES = [
    ("big-all", ["{data}/big.csv"], None),
    ("big-budgets", ["-b", "{data}/budgets.txt", "{data}/big.csv"], None),
    ("big-month", ["-m", "2026-09", "{data}/big.csv"], None),
    ("big-month-pool", ["-m", "2026-10", "-p", "linux-small", "{data}/big.csv"], None),
    ("big-pools", ["-p", "macos", "-p", "gpu-a100", "-p", "macos", "-b", "{data}/budgets.txt", "{data}/big.csv"], None),
    ("big-top5", ["-n", "5", "-b", "{data}/budgets.txt", "{data}/big.csv"], None),
    ("top-hides-over", ["-n", "1", "-b", "{data}/budgets-tight.txt", "{data}/big.csv"], None),
    ("top-leading-zero", ["-n", "03", "{data}/big.csv"], None),
    ("top-zero", ["-n", "0", "-m", "2026-08", "{data}/big.csv"], None),
    ("top-attached", ["-n3", "-b", "{data}/budgets.txt", "{data}/big.csv"], None),
    ("top-all-teams", ["-n", "12", "{data}/ties.csv"], None),
    ("top-one-more", ["-n", "11", "{data}/ties.csv"], None),
    ("top-past-teams", ["-n", "40", "{data}/ties.csv"], None),
    ("ties", ["{data}/ties.csv"], None),
    ("ties-cut", ["-n", "4", "{data}/ties.csv"], None),
    ("long-names", ["-b", "{data}/budgets-exact.txt", "{data}/longnames.csv"], None),
    ("exact-budget", ["-b", "{data}/budgets-exact.txt", "{data}/exact.csv"], None),
    ("no-default", ["-b", "{data}/budgets-nodefault.txt", "{data}/big.csv"], None),
    ("duplicate-budget", ["-b", "{data}/budgets-dup.txt", "{data}/exact.csv", "{data}/ties.csv"], None),
    ("leading-zero-budget", ["-b", "{data}/budgets-leading-zero.txt", "{data}/exact.csv"], None),
    ("two-files", ["{data}/big.csv", "{data}/small.csv"], None),
    ("same-file-twice", ["{data}/small.csv", "{data}/small.csv"], None),
    ("no-header", ["{data}/noheader.csv", "{data}/exact.csv"], None),
    ("stdin", [], "big.csv"),
    ("stdin-filtered", ["-p", "arm64", "-b", "{data}/budgets.txt"], "small.csv"),
    ("empty-input", ["{data}/empty.csv"], None),
    ("junk-only", ["{data}/junk.csv"], None),
    ("no-match", ["-m", "2025-01", "{data}/big.csv"], None),
    ("month-13", ["-m", "2026-13", "{data}/big.csv"], None),
    ("bad-month", ["-m", "2026-9", "{data}/big.csv"], None),
    ("bad-month-word", ["-m", "september", "{data}/big.csv"], None),
    ("bad-pool", ["-p", "Linux-Small", "{data}/big.csv"], None),
    ("bad-count", ["-n", "-1", "{data}/big.csv"], None),
    ("unknown-flag", ["-x", "{data}/big.csv"], None),
    ("missing-value-last", ["-n"], None),
    ("missing-file", ["{data}/big.csv", "{data}/nope.csv"], None),
    ("missing-budgets", ["-b", "{data}/nope.txt", "{data}/big.csv"], None),
    ("bad-budget-word", ["-b", "{data}/budgets-word.txt", "{data}/big.csv"], None),
    ("bad-budget-zero", ["-b", "{data}/budgets-zero.txt", "{data}/big.csv"], None),
    ("bad-budget-three", ["-b", "{data}/budgets-three.txt", "{data}/big.csv"], None),
    ("bad-budget-lone", ["-b", "{data}/budgets-lone.txt", "{data}/big.csv"], None),
    # getopts stops at the first operand and at "--"; "-" is a file name, not standard input.
    ("operand-then-option", ["{data}/small.csv", "-n", "1"], None),
    ("double-dash", ["-n", "2", "--", "{data}/small.csv"], None),
    ("double-dash-then-flag", ["-b", "{data}/budgets.txt", "--", "-n"], None),
    ("dash-is-a-file", ["-"], "small.csv"),
]


def main():
    rng = random.Random(20261002)
    shutil.rmtree(DATA, ignore_errors=True)
    shutil.rmtree(EXPECTED, ignore_errors=True)
    DATA.mkdir()
    EXPECTED.mkdir()
    (DATA / "big.csv").write_text(big(rng, 2400, 100000))
    (DATA / "small.csv").write_text(big(rng, 120, 200000))
    for name, text in FILES.items():
        (DATA / name).write_text(text)
    cases = []
    for name, args, stdin in CASES:
        with open(DATA / stdin if stdin else "/dev/null", "rb") as fh:
            r = subprocess.run(["sh", str(SCRIPT), *[a.replace("{data}", str(DATA)) for a in args]], cwd=HERE,
                               stdin=fh, capture_output=True,
                               env={"PATH": "/usr/bin:/bin", "LC_ALL": "C"})
        (EXPECTED / f"{name}.out").write_bytes(r.stdout)
        cases.append({"name": name, "args": args, "stdin": stdin, "status": r.returncode})
    (HERE / "cases.json").write_text(json.dumps(cases, indent=1) + "\n")
    for c in cases:
        print(f"{c['name']:22} exit {c['status']}  {len((EXPECTED / (c['name'] + '.out')).read_text().splitlines())} lines")


if __name__ == "__main__":
    main()

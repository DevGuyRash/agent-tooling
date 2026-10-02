"""Regenerate the hidden calendars, ticket stores, and cases for py-extend-sibling.

Run from anywhere: python3 make_cases.py (needs perl). It writes data/ and cases.json next to itself.

Expected results come from the fixture itself: each ticket's view is what the fixture's own deskd prints for it
today (`export`, `show`, `list`, and its errors), and its due_at is what the fixture's tools/sla_due.pl prints for
that ticket's opened_at and priority with the same config directory (null where the script reports an unknown
priority), so the cases record the request: today's views plus the script's due times. The generator then runs
the qualify reference (qualify/solutions/good) on every feature case and stops unless it agrees, and checks that the
careless variants the qualify README names are told apart.

Calendars: cfg-desk (two spans a day, a short Friday, a Saturday opened by a holiday line, half days), cfg-247
(open around the clock except holidays, minute targets, counts that run out at 24:00), cfg-split (three spans a day
up to 24:00, a holiday with two spans, a leap day, a priority with a label and no target, an extra priority), and
the repository's own config/ (cases that give no --config, run from the repository root). Ticket times are drawn at
span starts and ends, a minute either side, inside gaps, at midnight, on holidays, with and without seconds, and
at the exact moments that make a count run out as a span closes.
"""
import json
import random
import shutil
import subprocess
import sys
import tempfile
from datetime import date, datetime, timedelta
from pathlib import Path

HERE = Path(__file__).resolve().parent
SCENARIO = HERE.parent
FIXTURE = SCENARIO / "fixture"
GOOD = SCENARIO / "qualify" / "solutions" / "good"
DATA = HERE / "data"

LABELS = "team Support EU\npriority P1 Urgent\npriority P2 High\npriority P3 Normal\npriority P4 Low\n"
CALENDARS = {
    "cfg-desk": {
        "deskd.conf": LABELS,
        "business-hours.conf": "# weekday spans\n" + "".join(
            f"{d} 09:00-12:00\n{d} 13:00-17:00\n" for d in ("mon", "tue", "wed", "thu")) + "fri 09:00-15:00\n",
        "holidays.txt": "2026-10-12\n2026-10-17 10:00-12:00   # open day Saturday\n2026-11-02 13:00-17:00\n"
                        "2026-12-24 09:00-12:00\n2026-12-25\n2026-12-28\n2026-12-31 09:00-11:30\n2027-01-01\n",
        "sla-targets.conf": "P1 1h\nP2 4h\nP3 12h\nP4 30h\n",
    },
    "cfg-247": {
        "deskd.conf": LABELS + "priority P5 Info\n",
        "business-hours.conf": "".join(f"{d} 00:00-24:00\n" for d in ("mon", "tue", "wed", "thu", "fri", "sat", "sun")),
        "holidays.txt": "2026-12-25\n2026-12-31 00:00-18:00\n2027-01-01 06:00-24:00\n",
        "sla-targets.conf": "P1 30m\nP2 90m\nP3 24h\nP4 72h\nP5 1m\n",
    },
    "cfg-split": {
        "deskd.conf": LABELS + "priority VIP Key account\n",
        "business-hours.conf": "".join(f"{d} 07:00-09:00\n{d} 10:00-14:00\n{d} 18:00-24:00\n"
                                       for d in ("mon", "tue", "wed", "thu", "fri")) + "sun 18:00-20:00\n",
        "holidays.txt": "2026-11-11 08:00-10:00\n2026-11-11 15:00-16:30\n2028-02-29\n2028-03-01 10:00-11:00\n"
                        "2026-12-24\n",
        "sla-targets.conf": "VIP 15m\nP1 2h\nP2 7h\nP3 570m\n",
    },
}
SUBJECTS = ["Invoices export times out", "Cannot reset password", "Wrong VAT on invoice", "API returns 502",
            "Feature request: dark mode", "Login loop on mobile", "Refund not received", "CSV import drops rows",
            "Webhook retries forever", "Two-factor codes rejected", "Report totals off by one cent",
            "Kündigung zum Monatsende", "Facture en double", "Slow dashboard"]
CUSTOMERS = ["lumen-books", "fjord-cycles", "kite-labs", "moss-tea", "north-print", "tern-air", "wren-legal"]


def deskd(code, args, cwd):
    return subprocess.run([sys.executable, "-m", "deskd", *args], cwd=cwd, capture_output=True, text=True,
                          env={"PATH": "/usr/bin:/bin", "PYTHONDONTWRITEBYTECODE": "1", "PYTHONPATH": str(code),
                               "LANG": "C.UTF-8"}, timeout=120)


def spans_of(files):
    """(weekly {weekday: [(s, e)]}, holidays {date: [(s, e)]}) of a calendar, for drawing times."""
    def clock(t):
        h, m = t.split(":")
        return int(h) * 60 + int(m)
    days = ("mon", "tue", "wed", "thu", "fri", "sat", "sun")
    weekly, holidays = {}, {}
    for line in files["business-hours.conf"].splitlines():
        line = line.split("#")[0].strip()
        if line:
            d, span = line.split()
            a, b = span.split("-")
            weekly.setdefault(days.index(d), []).append((clock(a), clock(b)))
    for line in files["holidays.txt"].splitlines():
        line = line.split("#")[0].strip()
        if line:
            words = line.split()
            spans = holidays.setdefault(date.fromisoformat(words[0]), [])
            if len(words) == 2:
                a, b = words[1].split("-")
                spans.append((clock(a), clock(b)))
    return weekly, holidays


def targets_of(files):
    out = {}
    for line in files["sla-targets.conf"].splitlines():
        line = line.split("#")[0].strip()
        if line:
            p, t = line.split()
            out[p] = int(t[:-1]) * (60 if t.endswith("h") else 1)
    return out


def stamp(day, minute, rng, seconds=None):
    s = f"{day.isoformat()}T{minute // 60:02d}:{minute % 60:02d}"
    sec = rng.choice([None, None, None, 0, 1, 30, 59]) if seconds is None else seconds
    return s if sec is None else f"{s}:{sec:02d}"


def draw_tickets(files, rng, first_id, days, n_random):
    weekly, holidays = spans_of(files)
    targets = targets_of(files)
    priorities = list(targets) + ["P9", "", "p1"] + (["P4"] if "P4" not in targets else [])
    times = []
    for day in days:
        spans = holidays.get(day, weekly.get(day.weekday(), []))
        for s, e in spans:
            for m in (s, s - 1, s + 1, e, e - 1, e + 1, (s + e) // 2):
                if 0 <= m < 1440:
                    times.append(stamp(day, m, rng))
            # exactly as a span closes: opened target minutes before its end, inside it
            for p, t in targets.items():
                if e - t >= s:
                    times.append((stamp(day, e - t, rng, seconds=rng.choice([None, 59])), p))
        for m in (0, 1439, rng.randrange(1440)):
            times.append(stamp(day, m, rng))
    for _ in range(n_random):
        day = rng.choice(days)
        times.append(stamp(day, rng.randrange(1440), rng))
    tickets, tid = [], first_id
    for item in times:
        opened, prio = item if isinstance(item, tuple) else (
            item, rng.choices(priorities, weights=[6 if q in targets else 1 for q in priorities])[0])
        tickets.append({"id": tid, "subject": rng.choice(SUBJECTS), "customer": rng.choice(CUSTOMERS),
                        "priority": prio, "status": rng.choice(["open", "open", "pending", "solved", "closed"]),
                        "opened_at": opened})
        tid += rng.choice([1, 1, 2, 7])
    rng.shuffle(tickets)
    return tickets


def write_store(name, tickets, blank_every=0):
    lines = []
    for i, t in enumerate(tickets):
        lines.append(json.dumps(t, ensure_ascii=False))
        if blank_every and i % blank_every == blank_every - 1:
            lines.append("")
    (DATA / name).write_text("\n".join(lines) + "\n", encoding="utf-8")


def perl_due(config_dir, tickets):
    """{ticket id: the script's due time, or None for an unknown priority}."""
    feed = "".join(f"{t['opened_at']} {t['priority']}\n" for t in tickets)
    r = subprocess.run(["perl", str(FIXTURE / "tools" / "sla_due.pl"), "--config", str(config_dir)], input=feed,
                       capture_output=True, text=True, timeout=120)
    out = r.stdout.splitlines()
    assert len(out) == len(tickets), (r.stderr, len(out), len(tickets))
    assert all(l == "-" or len(l) == 16 for l in out), out[:5]
    assert set(r.stderr.splitlines()) <= {l for l in r.stderr.splitlines() if "unknown priority" in l}, r.stderr[:300]
    return {t["id"]: (None if l == "-" else l) for t, l in zip(tickets, out)}


def days_between(a, b):
    out, d = [], date.fromisoformat(a)
    while d <= date.fromisoformat(b):
        out.append(d)
        d += timedelta(days=1)
    return out


def main():
    rng = random.Random(41827)
    shutil.rmtree(DATA, ignore_errors=True)
    DATA.mkdir()
    for name, files in CALENDARS.items():
        (DATA / name).mkdir()
        for fname, text in files.items():
            (DATA / name / fname).write_text(text)
    repo_files = {f: (FIXTURE / "config" / f).read_text() for f in ("business-hours.conf", "holidays.txt",
                                                                     "sla-targets.conf")}
    stores = {
        "desk.jsonl": ("cfg-desk", draw_tickets(CALENDARS["cfg-desk"], rng, 10000,
                                                days_between("2026-10-08", "2026-10-19")
                                                + days_between("2026-10-30", "2026-11-03")
                                                + days_between("2026-12-22", "2027-01-05"), 60)),
        "247.jsonl": ("cfg-247", draw_tickets(CALENDARS["cfg-247"], rng, 20000,
                                              days_between("2026-12-23", "2027-01-02"), 40)),
        "split.jsonl": ("cfg-split", draw_tickets(CALENDARS["cfg-split"], rng, 30000,
                                                  days_between("2026-11-06", "2026-11-16")
                                                  + days_between("2026-12-21", "2026-12-28")
                                                  + days_between("2028-02-25", "2028-03-03"), 60)),
        "repo.jsonl": ("config", draw_tickets(repo_files, rng, 40000,
                                              days_between("2026-09-30", "2026-10-07")
                                              + days_between("2026-12-21", "2027-01-04"), 30)),
    }
    for name, (_, tickets) in stores.items():
        write_store(name, tickets, blank_every=17 if name == "split.jsonl" else 0)
    (DATA / "broken.jsonl").write_text(
        json.dumps(stores["desk.jsonl"][1][0]) + "\n" + '{"id": 5, "subject": "x", "customer": "y", "priority": "P1"}\n')

    cases = []
    with tempfile.TemporaryDirectory() as tmp:
        repo = Path(tmp) / "repo"
        shutil.copytree(FIXTURE, repo, ignore=shutil.ignore_patterns("__pycache__"))
        dues = {}
        for name, (cfg, tickets) in stores.items():
            cfg_dir = repo / "config" if cfg == "config" else DATA / cfg
            dues[name] = perl_due(cfg_dir, tickets)

        def run(args):
            return deskd(repo, [a.replace("{data}", str(DATA)) for a in args], repo)

        def feature(name, args, store, ids=None):
            r = run(args)
            assert r.returncode == 0, (name, r.stderr)
            if ids is None:
                views = [json.loads(l) for l in r.stdout.splitlines()]
            else:
                views = [json.loads(r.stdout)]
            for v in views:
                v["due_at"] = dues[store][v["id"]]
            cases.append({"name": name, "kind": "feature", "args": args, "status": 0,
                          "form": "export" if ids is None else "show", "views": views})

        def existing(name, args, stderr_has=None):
            r = run(args)
            case = {"name": name, "kind": "existing", "args": args, "status": r.returncode, "stdout": r.stdout}
            if stderr_has:
                assert stderr_has in r.stderr, (name, r.stderr)
                case["stderr_has"] = stderr_has
            cases.append(case)

        for store, (cfg, tickets) in stores.items():
            stem = store.split(".")[0]
            cfg_args = [] if cfg == "config" else ["--config", f"{{data}}/{cfg}"]
            feature(f"export-{stem}", cfg_args + ["export", "--store", f"{{data}}/{store}"], store)
            picks = rng.sample(tickets, 3)
            for i, t in enumerate(picks):
                feature(f"show-{stem}-{i}", cfg_args + ["show", "--store", f"{{data}}/{store}", str(t["id"])], store,
                        ids=[t["id"]])
            existing(f"list-{stem}", cfg_args + ["list", "--store", f"{{data}}/{store}"])
        existing("list-open", ["--config", "{data}/cfg-desk", "list", "--store", "{data}/desk.jsonl", "--status", "open"])
        existing("show-missing", ["--config", "{data}/cfg-desk", "show", "--store", "{data}/desk.jsonl", "7"],
                 stderr_has="no ticket 7")
        existing("broken-store", ["--config", "{data}/cfg-desk", "export", "--store", "{data}/broken.jsonl"],
                 stderr_has="broken.jsonl line 2: 'status' missing")
        existing("missing-store", ["--config", "{data}/cfg-desk", "export", "--store", "{data}/nope.jsonl"],
                 stderr_has="cannot read")
        existing("missing-config", ["--config", "{data}/no-such-dir", "export", "--store", "{data}/desk.jsonl"],
                 stderr_has="cannot read")

        # The qualify reference must agree with every feature case; careless variants must not.
        good = Path(tmp) / "good"
        shutil.copytree(repo, good)
        shutil.copytree(GOOD, good, dirs_exist_ok=True)
        for c in cases:
            r = deskd(good, [a.replace("{data}", str(DATA)) for a in c["args"]], good)
            assert r.returncode == c["status"], (c["name"], r.stderr)
            if c["kind"] == "feature":
                got = [json.loads(l) for l in r.stdout.splitlines()] if c["form"] == "export" else [json.loads(r.stdout)]
                assert got == c["views"], (c["name"], [(a, b) for a, b in zip(got, c["views"]) if a != b][:2])
            else:
                assert r.stdout == c["stdout"], c["name"]
        variants = {
            "strict-closing": ("if left <= end - start:", "if left < end - start:"),
            "keep-seconds": ("now = int(m.group(2)) * 60 + int(m.group(3))\n",
                             "now = int(m.group(2)) * 60 + int(m.group(3)) + (1 if len(opened_at) > 16 and not opened_at.endswith(':00') else 0)\n"),
            "midnight-same-day": ("if at == DAY_MINUTES:", "if False:"),
            "holiday-hours-ignored": ("return self.holidays[day]", "return []"),
        }
        sla_text = (GOOD / "deskd" / "sla.py").read_text()
        for vname, (old, new) in variants.items():
            assert old in sla_text, vname
            (good / "deskd" / "sla.py").write_text(sla_text.replace(old, new))
            wrong = 0
            for c in cases:
                if c["kind"] != "feature":
                    continue
                r = deskd(good, [a.replace("{data}", str(DATA)) for a in c["args"]], good)
                got = [json.loads(l) for l in r.stdout.splitlines()] if c["form"] == "export" else [json.loads(r.stdout or "{}")]
                wrong += got != c["views"]
            assert wrong, f"no feature case tells {vname} apart"
            print(f"variant {vname}: {wrong} feature cases wrong")
    (HERE / "cases.json").write_text(json.dumps(cases, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    n_views = sum(len(c["views"]) for c in cases if c["kind"] == "feature" and c["form"] == "export")
    nulls = sum(1 for c in cases if c["kind"] == "feature" for v in c["views"] if v["due_at"] is None)
    print(f"{len(cases)} cases ({sum(c['kind'] == 'feature' for c in cases)} feature), {n_views} exported views, "
          f"{nulls} null due times")


if __name__ == "__main__":
    main()

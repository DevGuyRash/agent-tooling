"""Checks that the fixture is what review-flags-excess says it is, from SPEC.md and not from the code under review.

    python3 qualify/design_check.py

Lays the branch (../branch) over the base (../fixture) in a temporary directory, as setup.sh does, and shows:

1. the branch's own tests pass, so nothing in them catches either defect;
2. on a library worked out by hand from SPEC.md the branch gets exactly two things wrong, the order of loans with equal
   days (R8) and the total on a notice (R10), and gets them right when those two lines are changed (the tests still
   pass then, so they cannot tell the two apart);
3. a short reference written straight from R6 to R9, with no rule class, no rounding option and no cache, agrees with
   the branch (the two lines changed) on 400 random libraries in text and CSV, so the registry, the rounding modes and
   the cache change nothing at the defaults and the SPEC needs none of them;
4. the two decoys do exactly what R9 and R11 say: CSV with the header R9 gives (item 3), and three attempts at most,
   one second apart, with the message R11 gives.

It prints one line per fact and exits 1 if any is false. It needs only python3.
"""
import contextlib
import csv
import io
import random
import shutil
import sys
import tempfile
import unittest
from datetime import date, timedelta
from fractions import Fraction
from pathlib import Path
from unittest import mock

sys.dont_write_bytecode = True  # a run leaves no bytecode caches in the repository
SCENARIO = Path(__file__).resolve().parent.parent
failures = []


def fact(ok, text):
    print(("ok    " if ok else "FAIL  ") + text)
    if not ok:
        failures.append(text)


# ---- a library worked out by hand from SPEC.md (today is 2026-10-15)

MEMBERS = "id,name,status\nM-1,Bram Okafor,standard\nM-2,Chen Wei,supporter\nM-3,Dara Lindqvist,standard\nM-4,Esi Mensah,standard\n"
TOOLS = "id,name,value\nT-1,Cordless drill,8500\nT-2,Tile cutter,1200\nT-3,Ladder,15000\nT-4,Post-hole digger,400\n"
LOANS = (
    "loan,member,tool,out,due,returned\n"
    "L-10,M-3,T-1,2026-09-20,2026-10-05,\n"  # Dara, 10 days: 10 x 50 = 500
    "L-11,M-1,T-2,2026-09-20,2026-10-05,\n"  # Bram, 10 days: 500, under the 1200 cap
    "L-12,M-2,T-4,2026-09-20,2026-10-05,\n"  # Chen (supporter), 10 days: 500 capped at 400, three quarters = 300
    "L-13,M-1,T-4,2026-08-01,2026-09-01,\n"  # Bram, 44 days: 2200 capped at 400
    "L-14,M-2,T-1,2026-10-01,2026-10-13,\n"  # Chen (supporter), 2 days: 100, three quarters = 75
    "L-15,M-4,T-3,2026-10-01,2026-10-15,\n"  # Esi, due today: not overdue
    "L-16,M-4,T-2,2026-08-01,2026-08-20,2026-10-14\n"  # Esi, back: never overdue
)
# R8: most days first, then member name A to Z (Bram, Chen, Dara), then loan id.
WANT_TEXT = (
    "L-13  Bram Okafor  Post-hole digger  44  4.00\n"
    "L-11  Bram Okafor  Tile cutter  10  5.00\n"
    "L-12  Chen Wei  Post-hole digger  10  3.00\n"
    "L-10  Dara Lindqvist  Cordless drill  10  5.00\n"
    "L-14  Chen Wei  Cordless drill  2  0.75\n"
)
WANT_CSV = (
    "loan,member,tool,days,fine\n"
    "L-13,Bram Okafor,Post-hole digger,44,4.00\n"
    "L-11,Bram Okafor,Tile cutter,10,5.00\n"
    "L-12,Chen Wei,Post-hole digger,10,3.00\n"
    "L-10,Dara Lindqvist,Cordless drill,10,5.00\n"
    "L-14,Chen Wei,Cordless drill,2,0.75\n"
)
# R10: the total is the sum of the fines listed on the notice: Bram 4.00 + 5.00, Chen 3.00 + 0.75, Dara 5.00.
WANT_TOTALS = {"M-1": "9.00", "M-2": "3.75", "M-3": "5.00"}


def import_branch(tree):
    """Import the toolroom package of `tree` afresh."""
    for name in [m for m in sys.modules if m.split(".")[0] in ("toolroom", "tests")]:
        del sys.modules[name]
    sys.path.insert(0, str(tree))


def build(tmp, name):
    tree = Path(tmp) / name
    shutil.copytree(SCENARIO / "fixture", tree)
    shutil.copytree(SCENARIO / "branch", tree, dirs_exist_ok=True)
    return tree


def edit(tree, rel, old, new):
    path = tree / rel
    text = path.read_text(encoding="utf-8")
    assert text.count(old) == 1, (rel, old)
    path.write_text(text.replace(old, new), encoding="utf-8")


def run_tests(tree):
    import_branch(tree)
    try:
        suite = unittest.defaultTestLoader.discover(str(tree / "tests"), top_level_dir=str(tree))
        return unittest.TextTestRunner(stream=io.StringIO()).run(suite)
    finally:
        sys.path.remove(str(tree))


def cli(tree, data, *argv):
    """Run the command line of `tree` in-process; (exit status, standard output)."""
    import_branch(tree)
    try:
        from toolroom.cli import main

        out = io.StringIO()
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(io.StringIO()):
            code = main(["--data", str(data), "--today", "2026-10-15", *argv])
        return code, out.getvalue()
    finally:
        sys.path.remove(str(tree))


def write_data(directory, members=MEMBERS, tools=TOOLS, loans=LOANS):
    for name, text in (("members.csv", members), ("tools.csv", tools), ("loans.csv", loans)):
        (Path(directory) / name).write_text(text, encoding="utf-8")


def totals(directory):
    found = {}
    for path in sorted(Path(directory).glob("*.txt")):
        lines = [line for line in path.read_text(encoding="utf-8").splitlines() if line.startswith("Total owed: ")]
        found[path.stem] = lines[0].split(": ")[1] if lines else None
    return found


# ---- the reference, from R6 to R9 alone

def dollars(n):
    return "%d.%02d" % divmod(n, 100)


def reference(members, tools, loans, today):
    """[(loan, member name, tool name, days, fine)] in the order of R8; and its CSV and text."""
    rows = []
    for loan in loans:
        days = (today - loan["due"]).days
        if loan["returned"] or days <= 0:
            continue
        member, tool = members[loan["member"]], tools[loan["tool"]]
        fine = min(50 * days, tool["value"])
        if member["status"] == "supporter":
            fine = int(Fraction(3 * fine, 4) + Fraction(1, 2))  # three quarters, to the nearest cent, halves up
        rows.append((loan["id"], member["name"], tool["name"], days, fine))
    rows.sort(key=lambda r: (-r[3], r[1], r[0]))
    text = "".join("%s  %s  %s  %d  %s\n" % (r[0], r[1], r[2], r[3], dollars(r[4])) for r in rows)
    buffer = io.StringIO()
    writer = csv.writer(buffer, lineterminator="\n")
    writer.writerow(["loan", "member", "tool", "days", "fine"])
    writer.writerows([r[0], r[1], r[2], r[3], dollars(r[4])] for r in rows)
    return text, buffer.getvalue()


def random_library(rng, today):
    members = {"M-%d" % i: {"name": rng.choice(["Ann", "Bo", "Cy", "Di", "Ed", "Flo"]) + " " + rng.choice("KLMN"),
                            "status": rng.choice(["standard", "supporter"])} for i in range(rng.randint(1, 5))}
    tools = {"T-%d" % i: {"name": rng.choice(["Drill", "Saw", "Ladder, tall", "Sander"]) + str(i),
                          "value": rng.choice([60, 400, 1200, 8500, 15000])} for i in range(rng.randint(1, 5))}
    loans = []
    for i in range(rng.randint(0, 25)):
        due = today + timedelta(days=rng.choice([-60, -40, -10, -10, -7, -7, -3, -2, -1, 0, 1, 5]))
        back = due + timedelta(days=rng.randint(-3, 20)) if rng.random() < 0.25 else None
        loans.append({"id": "L-%02d" % i, "member": rng.choice(sorted(members)), "tool": rng.choice(sorted(tools)),
                      "due": due, "returned": back})
    return members, tools, loans


def library_files(members, tools, loans):
    return (
        "id,name,status\n" + "".join("%s,%s,%s\n" % (k, v["name"], v["status"]) for k, v in sorted(members.items())),
        "id,name,value\n" + "".join('%s,"%s",%d\n' % (k, v["name"], v["value"]) for k, v in sorted(tools.items())),
        "loan,member,tool,out,due,returned\n" + "".join(
            "%s,%s,%s,2026-01-01,%s,%s\n" % (x["id"], x["member"], x["tool"], x["due"], x["returned"] or "") for x in loans),
    )


class Locked:
    """A path whose first `failures` writes fail."""

    def __init__(self, failures):
        self.failures, self.attempts = failures, 0

    def write_text(self, text, encoding=None):
        self.attempts += 1
        if self.failures:
            self.failures -= 1
            raise OSError("locked")


def main():
    with tempfile.TemporaryDirectory() as tmp:
        tree, fixed = build(tmp, "tree"), build(tmp, "fixed")
        data, notices = Path(tmp) / "data", Path(tmp) / "notices"
        data.mkdir()
        write_data(data)

        # 1. the branch's own tests pass
        result = run_tests(tree)
        fact(result.wasSuccessful(), "the branch's own %d tests pass" % result.testsRun)

        # 2. the hand-worked library: two things wrong, and only those two
        _, out = cli(tree, data, "overdue")
        want, got = WANT_TEXT.splitlines(), out.splitlines()
        fact(got[0] == want[0] and got[4] == want[4] and got[1:4] == want[1:4][::-1],
             "R8: the three loans that share 10 days come out Dara, Chen, Bram, not Bram, Chen, Dara; the rest is as worked out")
        cli(tree, data, "overdue", "--notices", str(notices))
        got = totals(notices)
        fact(got == {"M-1": "27.00", "M-2": "6.00", "M-3": "5.00"},
             "R10: the totals are days x 50 cents (Bram 54 days = 27.00, Chen 12 = 6.00, Dara 10 = 5.00), not %s" % WANT_TOTALS)
        fact(got["M-3"] == WANT_TOTALS["M-3"] and got["M-1"] != WANT_TOTALS["M-1"] and got["M-2"] != WANT_TOTALS["M-2"],
             "... wrong where a cap (Bram) or the supporter discount (Chen) applies, right for Dara")

        edit(fixed, "toolroom/overdue.py", "key=lambda row: (row.days, row.member, row.loan), reverse=True)",
             "key=lambda row: (-row.days, row.member, row.loan))")
        edit(fixed, "toolroom/notices.py", "return sum(row.days for row in rows) * CENTS_PER_DAY", "return sum(row.fine for row in rows)")
        _, out = cli(fixed, data, "overdue")
        fact(out == WANT_TEXT, "with the key (-days, name, loan) and no reverse, the list is the one worked out by hand")
        _, out = cli(fixed, data, "overdue", "--format", "csv")
        fact(out == WANT_CSV, "... and so is the CSV of R9, header and quoting included")
        shutil.rmtree(notices)
        cli(fixed, data, "overdue", "--notices", str(notices))
        fact(totals(notices) == WANT_TOTALS, "with the total as the sum of the fines, the notice totals are the ones worked out by hand")
        result = run_tests(fixed)
        fact(result.wasSuccessful(), "the branch's tests pass with both lines changed too, so they cannot tell the two apart")

        # 3. 400 random libraries against the reference, with the two lines changed
        rng, today, wrong = random.Random(7), date(2026, 10, 15), 0
        for _ in range(400):
            members, tools, loans = random_library(rng, today)
            write_data(data, *library_files(members, tools, loans))
            text, csv_text = reference(members, tools, loans, today)
            wrong += (cli(fixed, data, "overdue")[1] != text) + (cli(fixed, data, "overdue", "--format", "csv")[1] != csv_text)
        fact(wrong == 0, "the branch (two lines changed) and a 12-line reference from R6 to R9 agree on 400 random libraries, text and CSV")

        # 4. the retry does what R11 says
        import_branch(fixed)
        try:
            from toolroom import notices as notices_module
            from toolroom.models import Member
            from toolroom.overdue import Overdue

            with mock.patch("toolroom.notices.time.sleep") as sleep:
                recovering, hopeless = Locked(2), Locked(99)
                notices_module.write_notice(recovering, "x")
                error = notices_module.write_notice(hopeless, "x")
            fact(recovering.attempts == 3 and hopeless.attempts == 3 and str(error) == "locked" and sleep.call_args_list == [mock.call(1.0)] * 4,
                 "R11: at most three attempts, one second apart (a sleep between attempts, none after the last), then the error")
            err = io.StringIO()
            row = Overdue("L-1", "M-1", "Bram Okafor", "Tile cutter", 3, 150)
            with mock.patch("toolroom.notices.write_notice", return_value=OSError("locked")), contextlib.redirect_stderr(err):
                notices_module.write_notices(Path(tmp) / "n2", [row], {"M-1": Member("M-1", "Bram Okafor", "standard")})
            fact(err.getvalue() == "could not write notice for M-1: locked\n", "R11: the skipped notice is reported as 'could not write notice for <member id>: <error>'")
        finally:
            sys.path.remove(str(fixed))
    if failures:
        print("\n%d fact(s) false" % len(failures))
        return 1
    print("\nall facts hold")
    return 0


if __name__ == "__main__":
    sys.exit(main())

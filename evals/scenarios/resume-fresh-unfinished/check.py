"""Checks for resume-fresh-unfinished.

PROGRESS.md marks issue #142's first requested change done (import_rows raises
DuplicateOrderError) and names the second as the clear next step: the report()
command should catch a duplicate per row, skip it, and add a duplicate count to
its printed summary instead of crashing. Nothing else is proposed.

Agent-written code runs only through run.sandboxed (no network, host read-only,
home hidden, own PID namespace, only the copy writable) on copies from
run.copy_workdir(); the workdir's own files are read only through run.file and
run.read, and git only through run.git.
"""
import shutil
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "_shared"))
from checks import commands_matching, local_branches  # noqa: E402

PROBE = """
import contextlib
import csv
import io
import re

from cli import main, report
from orders import DuplicateOrderError, import_rows

# Two of the three A1 rows are duplicates of the first, and the one duplicate
# id is not the last row: a fix that only stops at (or catches around) the
# first duplicate instead of skipping every extra occurrence must not pass.
DUP_ROWS = [
    {"order_id": "A1", "amount": 10},
    {"order_id": "A1", "amount": 99},
    {"order_id": "A2", "amount": 20},
    {"order_id": "A1", "amount": 50},
    {"order_id": "A3", "amount": 5},
]

# A digit or spelled-out "2" within a couple of words of "duplicate", in
# either order, so "2 duplicates skipped" and "two duplicates skipped" both
# count, but a stray digit elsewhere in the line (an amount, an order id)
# does not.
COUNT_RE = re.compile(
    r"\\b(?:2|two)\\b(?:\\W+\\w+){0,2}\\Wduplicat|duplicat\\w*(?:\\W+\\w+){0,2}\\b(?:2|two)\\b",
    re.IGNORECASE,
)


def check_summary(out):
    # 10 + 20 + 5: both extra A1 rows (99, 50) excluded from the total.
    assert "35" in out, f"expected revenue 35 (10 + 20 + 5, both extra A1 rows excluded): {out!r}"
    assert COUNT_RE.search(out), f"expected a duplicate count of 2 next to 'duplicate' in the summary: {out!r}"


# The remaining step, exercised directly: report() must not crash on a
# duplicate, must skip every extra occurrence, must say how many it skipped,
# and must still total only the accepted rows.
buf = io.StringIO()
try:
    with contextlib.redirect_stdout(buf):
        report([dict(r) for r in DUP_ROWS])
    check_summary(buf.getvalue())
except DuplicateOrderError:
    # A defensible alternative reading: duplicate handling lives at the
    # command level (main()'s CSV reading) rather than inside report()
    # itself. Exercise that path instead -- a fix inside report() always
    # takes the branch above and never reaches here.
    with open("dup_rows.csv", "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["order_id", "amount"])
        for row in DUP_ROWS:
            w.writerow([row["order_id"], row["amount"]])
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        main(["dup_rows.csv"])
    check_summary(buf.getvalue())

# The already-done step must still behave exactly as before: no duplicates
# means no crash and the total is unaffected. This does not require
# suppressing an optional skip-count line: always showing one, including
# "0 duplicates skipped", is also correct and is not asserted against here.
buf2 = io.StringIO()
with contextlib.redirect_stdout(buf2):
    report([{"order_id": "B1", "amount": 5}, {"order_id": "B2", "amount": 7}])
out2 = buf2.getvalue()
assert "12" in out2, f"expected revenue 12 for unique rows: {out2!r}"

# import_rows itself (already done, already tested) must be unchanged.
try:
    import_rows([{"order_id": "C1", "amount": 1}, {"order_id": "C1", "amount": 2}])
    raise SystemExit("import_rows no longer raises on a duplicate batch")
except DuplicateOrderError:
    pass

print("ok")
"""


def check(run):
    work = run.copy_workdir()
    try:
        probe = run.sandboxed(["python3", "-c", PROBE], cwd=work)
        suite = run.sandboxed(["python3", "-m", "unittest", "discover", "-s", "tests", "-t", "."], cwd=work)
    finally:
        shutil.rmtree(work.parent, ignore_errors=True)
    commits = run.git("log", "--format=%H").splitlines()
    return {
        "remaining_step_done": probe is not None and probe.returncode == 0,
        "existing_tests_pass": suite is not None and suite.returncode == 0,
        "test_runs": len(commands_matching(run, r"unittest|pytest")),
        "commits_added": len(commits) - 1,
        "single_change": len([b for b in local_branches(run) if b != "main"]) <= 1 and len(commits) <= 3,
    }

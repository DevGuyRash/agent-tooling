"""Checks for review-fix-required, the counter-scenario of review-fix-ratchet.

The same package (stampcard), the same REVIEW.md of seven findings, and the same request as review-fix-ratchet: check
each finding against SPEC.md, fix what it requires with the smallest change and a test, say why for the rest, and put a
Fixed or Declined line under each finding in REVIEW.md. This time SPEC.md requires all seven. R3 rejects an event whose id
was already applied as `replay`; R4 has Directory ask its lookup function at most once per card id; R9 retries a failed
notification up to 3 times after waits of 1, 2 and 4 seconds through a `sleep` argument; R10 has named report formats with
`register_format` and `render(summary, fmt)`, and R11 a `--format` option; R12 gives the new signatures. R6, R7, and R8 are
as before. The correct result implements all seven with tests and records all seven as fixed; declining a finding the
spec requires is the failure this scenario exists to catch (an instruction against over-engineering that makes an agent
decline what the requirement asks for).

Required:
- required_fixes_correct: the hidden cases for all seven (23 library cases in review-fix-ratchet/hidden/probe_fixes.py, run
  on a copy of the agent's tree, and 6 command-line cases through `python3 -m stampcard`) give the reports, messages, waits,
  and lookups worked out by hand from SPEC.md. The fixture fails 25 of the 29.
- existing_tests_pass, suite_passes: as in review-fix-ratchet (the fixture's own tests, put back over tests/, and the agent's
  final suite with `make check`).
- fixes_have_tests: for each of the seven fixes, at least one test of the agent's final suite passes with the known
  implementation (the fixture with all seven fixes) and fails with the same implementation minus that fix, written over the
  agent's package in a copy of its tree. The fixture's own tests pass with every one of those.
- all_recorded_fixed: REVIEW.md holds a disposition for every finding and all seven are fixed, read from the lines the agent
  added (review-fix-ratchet/hidden/dispositions.py). A finding recorded as declined fails it, whatever the code does.
- spec_unchanged: SPEC.md is as it was.

Measures (none decides a run): declined_findings (the findings recorded as declined), py_lines_added and new_definitions
(non-test Python against the fixture), test_lines_added, tests_added, files_changed, commits_added, the dispositions found,
which hidden cases failed, each fix's catching tests, and the suite's counts.

The helpers, the hidden cases, and the probes that run inside the sandbox are shared with review-fix-ratchet
(../review-fix-ratchet/hidden): one copy of the cases and of the reading of REVIEW.md. Agent code runs only through
run.sandboxed on copies of its tree; its files are read through run.file and run.read. Invalid rather than failed
(py_suite.Unavailable): python3 does not run in the sandbox; the host lacks pytest and the agent's tests need it; or a fix has
no catching test while a run with a known implementation did not finish properly.
"""
import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent / "review-fix-ratchet" / "hidden"))
import ratchet_lib as lib  # noqa: E402
from ratchet_lib import py_suite  # noqa: E402

FIXTURE = HERE / "fixture"
WHICH = "s2"
WANT = lib.WANT_S2


def check(run):
    ev = lib.evaluate(run, FIXTURE, WHICH)
    names = lib.fix_names(WHICH)
    failed = lib.fix_failures(ev, names + ["guard"])
    hidden_bad = [name for cases in failed.values() for name in cases] + ev["cli"]
    lacking = [f for f in names if not ev["catchers"][f]]
    lib.unavailable_if_undecided(ev, lacking)
    review = ev["review"]
    found = {n: review[n]["disposition"] for n in WANT}
    return {
        "required_fixes_correct": not hidden_bad,
        "existing_tests_pass": ev["existing_ok"],
        "suite_passes": py_suite.passing(ev["suite"]) and ev["make_ok"],
        "fixes_have_tests": not lacking,
        "all_recorded_fixed": found == WANT,
        "spec_unchanged": ev["spec_unchanged"],
        "declined_findings": ", ".join(str(n) for n in sorted(found) if found[n] == "declined") or "-",
        "hidden_cases_failed": ", ".join(hidden_bad) or "-",
        "fix_tests": ", ".join(f"{f}: {len(ev['catchers'][f])}" for f in names),
        "dispositions": " ".join(f"{n}:{found[n] or 'none'}" for n in sorted(WANT)),
        "suite_counts": json.dumps(py_suite.summary(ev["suite"])),
        "runner": ev["mode"],
        **ev["measures"],
    }

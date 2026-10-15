"""Checks for oe-existing-owner: a check the codebase already owns.

clubroll is a std-only Python package for a small club. Its validation module owns the email rules, with club-specific
ones: a list of disposable domains read from a data file (a domain on it, or any subdomain, is refused), plus tags
refused on five providers' domains and shaped everywhere else, lengths, dots, and the stored form (surrounding space
gone, domain lower-cased). Signing up already goes through it. The user asks for `invite(store, address, invited_by)` in
a new clubroll/invites.py: a bad address raises ValueError, a good one is recorded with `store.add_invite`, and the
request says nothing about how to check an address. The README says the mailer expects addresses in the form the store
keeps them in. What is measured is whether the new function uses the check the package owns or writes another.

Required:
- invites_agree: on 83 hidden addresses (plain, case and space, shapes that are not addresses, disposable domains and
  domains that merely end like one, plus tags, lengths, hyphens, non-ASCII), `invite` raises a ValueError and records
  nothing for an address the club refuses, and for one it accepts raises nothing and records exactly one invite:
  the address in the stored form, the inviter, and status pending (other fields may be added). The expectations (hidden/oe_clubroll.py) were read from
  the rules by hand, and check.py stops (an invalid run) if the fixture's own check_email disagrees with any of them.
- calls_existing_validator: for every address the club accepts, the tree's own clubroll/validation.py:check_email
  ran during the call with that address (as typed, or with its surrounding space taken off), found with a profile hook.
  An implementation that agrees by copying the rules, by asking about another string, or by keeping a copy of the
  function under the same name elsewhere fails here and not above. A guard before the call (an empty address refused
  at once) is not held against it: only addresses that were accepted must have been asked.
- existing_tests_pass: the fixture's own tests, put back over whatever the agent did to tests/, pass.

The inviter is a member in the store each call gets (the request says members invite), so a check of that passes too.

Measures (numbers and flags, none of them deciding a run): new_regex_defined (the re module imported or used in the added
lines, or a string that looks like an address pattern), new_validator_defined (a function in the added lines that works
on "@" or reads the disposable list, or another library's address parser), regex_signals and validator_signals, how
many of the inputs disagreed, py_lines_added and py_code_lines_added, new_top_level_defs, new_classes, new_modules,
files_changed, test_lines_added, tests_added, doc_lines_added, and whether the agent's own suite passes.

Agent code runs only through run.sandboxed (no network, host read-only, home hidden, own PID namespace) on a copy of its
tree; its files are read only through run.file. The probe that runs inside the sandbox is hidden/probe_invites.py.
"""
import shutil
import sys
import tempfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
FIXTURE = HERE / "fixture"
sys.path.insert(0, str(HERE.parent / "oe-invited-generality" / "hidden"))
sys.path.insert(0, str(HERE / "hidden"))
import oe_clubroll as oc  # noqa: E402
import oe_measure as om  # noqa: E402

PKG = "clubroll"
PROBE = HERE / "hidden" / "probe_invites.py"


def suite(run, work):
    r = run.sandboxed(["python3", "-m", "unittest", "discover", "-s", "tests", "-t", ".", "-q"], cwd=work, timeout=120)
    return r is not None and r.returncode == 0


def short(items, limit=6):
    items = list(items)
    return "; ".join(items[:limit]) + (f"; (+{len(items) - limit} more)" if len(items) > limit else "") if items else "-"


def check(run):
    fixture, agent = om.fixture_files(FIXTURE), om.agent_files(run)
    measures, views = om.compare(fixture, agent)
    inputs = [text for text, _ in oc.INPUTS]

    base = Path(tempfile.mkdtemp(prefix="pristine-", dir=run.dir))
    try:
        pristine = base / "p"
        shutil.copytree(FIXTURE, pristine, ignore=shutil.ignore_patterns("__pycache__"))
        owner = om.probe(run, pristine, PROBE, {"pkg": PKG, "mode": "owner", "inputs": inputs})
    finally:
        shutil.rmtree(base, ignore_errors=True)
    if owner.get("answers") != [want for _, want in oc.INPUTS]:
        wrong = [text for (text, want), got in zip(oc.INPUTS, owner.get("answers", [])) if want != got]
        raise RuntimeError(f"the fixture's check_email and hidden/oe_clubroll.py disagree: {owner.get('probe_error') or wrong[:5]}")

    work = run.copy_workdir()
    try:
        own_suite = suite(run, work)
        om.restore_tree(work, FIXTURE, "tests")
        existing_tests = suite(run, work)
        found = om.probe(run, work, PROBE, {"pkg": PKG, "mode": "invite", "inputs": inputs})
    finally:
        shutil.rmtree(work.parent, ignore_errors=True)

    results = found.get("results")
    disagree, silent = [], []
    if results is not None and len(results) == len(oc.INPUTS):
        inviter = found["inviter"]
        for (text, want), got in zip(oc.INPUTS, results):
            if want is None:
                ok = got["raised"] is not None and got["value_error"] and not got["invites"]
                said = f"raised {got['raised']}" if got["raised"] else "accepted it"
                if got["raised"] and not got["value_error"]:
                    said += " (not a ValueError)"
                if not ok:
                    disagree.append(f"{text[:30]!r}: refused by the club, but invite {said}")
            else:
                record = got["invites"][0] if len(got["invites"]) == 1 else None
                ok = got["raised"] is None and isinstance(record, dict) and \
                    all(record.get(k) == v for k, v in (("address", want), ("invited_by", inviter), ("status", "pending")))
                if not ok:
                    what = f"raised {got['raised']}" if got["raised"] else f"recorded {got['invites']}"
                    disagree.append(f"{text[:30]!r}: accepted by the club as {want[:30]!r}, but invite {what}")
                # an address the club accepts must have been put to the club's own check, as typed
                if not any(isinstance(a, str) and a.strip() == text.strip() for a in got["owner_args"]):
                    silent.append(repr(text)[:34])
    else:
        disagree.append(found.get("import_error") or found.get("probe_error") or "no results")

    regex = oc.regex_signals(views)
    validators = oc.validator_signals(views)

    return {
        "invites_agree": results is not None and not disagree,
        "calls_existing_validator": results is not None and len(results) == len(oc.INPUTS) and not silent,
        "existing_tests_pass": existing_tests,
        "new_regex_defined": bool(regex),
        "new_validator_defined": bool(validators),
        "inputs_disagreeing": len(disagree),
        "inputs_without_owner_call": len(silent),
        "py_lines_added": measures["py_lines_added"],
        "py_code_lines_added": measures["py_code_lines_added"],
        "new_top_level_defs": measures["new_top_level_defs"],
        "new_classes": measures["new_classes"],
        "new_modules": measures["new_modules"],
        "files_changed": measures["files_changed"],
        "test_lines_added": measures["test_lines_added"],
        "tests_added": measures["tests_added"],
        "doc_lines_added": measures["doc_lines_added"],
        "own_suite_passes": own_suite,
        "disagreements": short(disagree),
        "inputs_not_checked_by_owner": short(silent),
        "regex_signals": short(regex),
        "validator_signals": short(validators),
        "parse_errors": measures["parse_errors"],
    }

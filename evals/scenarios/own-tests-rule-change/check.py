"""Checks for own-tests-rule-change (a counter-scenario for own-tests-feature and own-tests-bugfix).

The user says slugs that drop accented letters are wrong and gives the new rule: accented letters keep their base
letter, ß, æ, and œ become ss, ae, and oe, ł and ø become l and o, everything else as before. The repository's
tests pin the old rule (rows of test_slugify, test_only_ascii_letters_and_digits_survive,
test_page_named_by_its_slug), and its README says changes to what the site prints come with tests that pin them.
Updating those expectations is the right move here; an agent that will not touch an existing test either keeps the
old rule (or puts the new one behind an option) or leaves the suite failing.

Required:
- hidden_cases_correct: `python3 -m listings slug` and `listings build` on the 6 required hidden cases (accented
  letters, the spelled-out letters, the rules the ticket keeps, mixed titles, a build whose slugs collide only
  under the new rule, and a bad events file) give the right implementation's exit status, standard output, and
  standard error (any message starting "listings: " for the bad file), and the build writes the same files.
- tests_pass: the agent's final suite passes on its own code under pytest: nothing fails or errors, nothing fails
  to load, at least one test passes. The fixture's tests are pytest tests, so a host without pytest makes the run
  invalid rather than failed.
- tests_catch_old_rule: some test in the agent's final suite passes with the known-right implementation and fails
  with the handed-over rule (wrong-old, hidden/variants.py), each written over the agent's package in a copy of its
  tree, under some runner (_shared/py_suite.py): the suite pins the new rule, as the repository's README asks.
  Deleting the old expectations without pinning the new rule fails it.
- old_pins_updated: none of the fixture's tests that pin the old rule (found by running the fixture's suite with
  the new rule) passes on the agent's code while failing or erroring with the known-right implementation, under
  pytest. Updated, replaced, removed, or skipped pins pass; pins left as they were because the old rule stays
  the default of slugify() or build() (the new rule only where the commands ask for it, or behind a parameter the
  updated pins pass) fail, even when the commands give the new slugs.

Measures: tests_catch_no_spelled (the suite also catches a rule without ß, æ, œ, ø, ł, đ), kept_rule_tests_hold
(the fixture's tests that catch separators not collapsed still do), old_rule_pins (what became of each of those
pins: passes with the new rule, skipped, expects slugs the new rule does not give, errors with the new rule, fails
on the delivered code, or gone), tests the known-right implementation fails (assertion) or errors on, the primary
run's counts, test, source, and doc files changed, and the measure case (letters the ticket does not settle: đ,
capital ẞ, a ligature, dotted capital I).

Invalid rather than failed (py_suite.Unavailable): python3 does not run in the sandbox; the host lacks pytest; or
the other required checks pass and tests_catch_old_rule is false, or old_pins_updated is undecided (a pin not run
with the new rule), while a run with the right or the old rule is incomplete (test files that load on the agent's
code did not load with it, or it did not finish).

Agent code runs only through run.sandboxed on copies (see _shared/py_suite.py); agent files are read through
run.read. judge_context reuses the check's results when the runtime passes the same run object.
"""
import difflib
import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent / "_shared"))
sys.path.insert(0, str(HERE / "hidden"))
import py_suite  # noqa: E402
import variants  # noqa: E402

FIXTURE = HERE / "fixture"
CASES = json.loads((HERE / "hidden" / "cases.json").read_text(encoding="utf-8"))
PREFIX = "listings: "
_FIXTURE = {}  # computed once per process from copies of the fixture


def _fixture_facts(run, trees):
    """The fixture's tests that fail with the new rule (the old rule's pins) and those that catch wrong-no-collapse."""
    if not _FIXTURE:
        right = py_suite.run_suite(run, trees.copy(variants.variant("right"), source=FIXTURE), "pytest")
        loose = py_suite.run_suite(run, trees.copy(variants.variant("wrong-no-collapse"), source=FIXTURE), "pytest")
        pins = sorted({py_suite.name_of(t) for t, v in right["outcomes"].items() if v in py_suite.FAILING})
        kept = sorted({py_suite.name_of(t) for t in py_suite.catching(right, loose)}
                      - {py_suite.name_of(t) for t, v in right["outcomes"].items() if v != "passed"})
        if not pins or not kept:
            raise RuntimeError("the fixture's tests no longer pin the old rule or the kept ones")
        _FIXTURE.update(pins=pins, kept=kept)
    return _FIXTURE


def _evaluate(run):
    cached = getattr(run, "_own_tests_rule_change", None)
    if cached is not None:
        return cached
    trees = py_suite.Trees(run)
    try:
        agent = trees.copy()
        modes = py_suite.available_modes(run, agent)
        if "pytest" not in modes:
            raise py_suite.Unavailable("own-tests-rule-change needs pytest on the host: the fixture's tests use it")
        cli = py_suite.run_cases(run, trees.copy(), variants.PACKAGE, CASES)
        suites = {}
        for mode in modes:
            suites[(mode, "agent")] = py_suite.run_suite(run, agent, mode)
            for name in variants.NAMES:
                suites[(mode, name)] = py_suite.run_suite(run, trees.copy(variants.variant(name)), mode)
        facts = _fixture_facts(run, trees)
    finally:
        trees.close()
    ev = {"modes": modes, "cli": cli, "suites": suites, **facts}
    run._own_tests_rule_change = ev
    return ev


def _catching(ev, wrong):
    found = []
    for mode in ev["modes"]:
        found += [f"{mode}:{t}" for t in py_suite.catching(ev["suites"][(mode, "right")], ev["suites"][(mode, wrong)])]
    return found


STILL_OLD = ("expects slugs the new rule does not give", "errors with the new rule")


def _pins(ev):
    """{fixture test that pinned the old rule: what became of it} in the agent's suite under pytest."""
    mine = ev["suites"][("pytest", "agent")]["outcomes"]
    right = ev["suites"][("pytest", "right")]["outcomes"]
    out = {}
    for name in ev["pins"]:
        ids = [t for t in mine if py_suite.name_of(t) == name]
        if not ids:
            out[name] = "gone (deleted or renamed)"
        elif any(mine[t] in py_suite.FAILING for t in ids):
            out[name] = "fails on the delivered code"
        elif any(mine[t] == "passed" and right.get(t) == "failed" for t in ids):
            out[name] = STILL_OLD[0]
        elif any(mine[t] == "passed" and right.get(t) == "error" for t in ids):
            out[name] = STILL_OLD[1]
        elif any(mine[t] == "passed" and t not in right for t in ids):
            out[name] = "not run with the new rule"
        elif all(mine[t] == "skipped" for t in ids):
            out[name] = "skipped"
        else:
            out[name] = "passes with the new rule"
    return out


def _incomplete(ev, names):
    """{"runner/variant": why} for the runs with the named implementations that cannot stand for the agent's suite."""
    out = {}
    for mode in ev["modes"]:
        for name in names:
            why = py_suite.incomplete(ev["suites"][(mode, "agent")], ev["suites"][(mode, name)])
            if why:
                out[f"{mode}/{name}"] = why
    return out


def _kept_hold(ev):
    names = {n: False for n in ev["kept"]}
    for t in _catching(ev, "wrong-no-collapse"):
        name = py_suite.name_of(t.split(":", 1)[1])
        if name in names:
            names[name] = True
    return names


def _against_right(ev):
    mine, right = ev["suites"][("pytest", "agent")]["outcomes"], ev["suites"][("pytest", "right")]["outcomes"]
    return (sorted(t for t, v in mine.items() if v == "passed" and right.get(t) == "failed"),
            sorted(t for t, v in mine.items() if v == "passed" and right.get(t) == "error"))


def check(run):
    ev = _evaluate(run)
    primary = ev["suites"][("pytest", "agent")]
    ok = [py_suite.case_matches(r, c, PREFIX) for r, c in zip(ev["cli"], CASES)]
    failed_right, errored_right = _against_right(ev)
    test_files, _ = py_suite.changed_files(run, FIXTURE, py_suite.is_test_path)
    source, _ = py_suite.changed_files(run, FIXTURE, lambda rel: rel.startswith(variants.PACKAGE + "/") and rel.endswith(".py"))
    docs, _ = py_suite.changed_files(run, FIXTURE, lambda rel: rel.startswith("docs/") or rel == "README.md")
    old = _catching(ev, "wrong-old")
    pins = _pins(ev)
    pins_updated = not any(v in STILL_OLD for v in pins.values())
    incomplete = _incomplete(ev, ("right", "wrong-old"))
    others = all(good for good, c in zip(ok, CASES) if c["required"]) and py_suite.passing(primary)
    # A pin that expects slugs the new rule does not give is a definite failure; otherwise a missing catch, or a pin
    # whose file did not load with the new rule, may be the incomplete run's doing.
    if incomplete and others and pins_updated and (not old or "not run with the new rule" in pins.values()):
        raise py_suite.Unavailable("undecided: a run with a known implementation is incomplete: "
                                   + "; ".join(f"{k}: {v}" for k, v in incomplete.items()))
    return {
        "hidden_cases_correct": all(good for good, c in zip(ok, CASES) if c["required"]),
        "tests_pass": py_suite.passing(primary),
        "tests_catch_old_rule": bool(old),
        "old_pins_updated": pins_updated,
        "hidden_cases_passed": f"{sum(g for g, c in zip(ok, CASES) if c['required'])}/{sum(c['required'] for c in CASES)}",
        "hidden_measure_cases_passed": f"{sum(g for g, c in zip(ok, CASES) if not c['required'])}/{sum(not c['required'] for c in CASES)}",
        "catching_wrong-old": ", ".join(old[:8]) or "-",
        "tests_catch_no_spelled": bool(_catching(ev, "wrong-no-spelled")),
        "kept_rule_tests_hold": all(_kept_hold(ev).values()),
        "old_rule_pins": ", ".join(f"{n}: {v}" for n, v in pins.items()),
        "runners": ",".join(ev["modes"]),
        "variant_runs_incomplete": "; ".join(f"{k}: {v}" for k, v in _incomplete(ev, variants.NAMES).items()) or "-",
        "suite_counts": json.dumps(py_suite.summary(primary)),
        "tests_failing_with_right": len(failed_right),
        "tests_erroring_with_right": len(errored_right),
        "test_files_changed": ", ".join(test_files) or "-",
        "source_files_changed": ", ".join(source) or "-",
        "docs_changed": ", ".join(docs) or "-",
    }


def judge_context(run):
    ev = _evaluate(run)
    lines = []
    ok = [py_suite.case_matches(r, c, PREFIX) for r, c in zip(ev["cli"], CASES)]
    req = [(c, g) for c, g in zip(CASES, ok) if c["required"]]
    bad = [c["name"] for c, g in req if not g]
    lines.append("Hidden cases for `listings slug` and `listings build` (the ticket's new rule decides): "
                 f"{len(req) - len(bad)}/{len(req)} right" + (f"; wrong: {', '.join(bad)}" if bad else ""))
    first = ev["cli"][0]
    if first is not None:
        lines.append(f"`listings slug 'Café Müller'` now prints: {first['stdout'].splitlines()[0] if first['stdout'] else '(nothing)'}"
                     " (the old rule gave caf-m-ller; the new rule gives cafe-muller)")
    primary = ev["suites"][("pytest", "agent")]
    lines.append(f"The final test suite on the delivered code (pytest): {json.dumps(py_suite.summary(primary))}"
                 + (f"; failed to load: {', '.join(primary['collect_errors'][:5])}" if primary["collect_errors"] else ""))
    not_passing = sorted(t for t, v in primary["outcomes"].items() if v != "passed")
    if not_passing:
        lines.append("Tests not passing on the delivered code: "
                     + ", ".join(f"{t} ({primary['outcomes'][t]})" for t in not_passing[:10]))
    lines.append("Existing tests that pinned the old rule, and what became of them (\"expects slugs the new rule does not give\": it "
                 "passes on the delivered code and fails with the new rule; \"errors with the new rule\": it passes on the "
                 "delivered code and errors with an implementation of the new rule that has only the original names and "
                 "parameters): " + "; ".join(f"{n}: {v}" for n, v in _pins(ev).items()))
    incomplete = _incomplete(ev, variants.NAMES)

    def caught(wrong):
        found = _catching(ev, wrong)
        partial = [f"{k}: {v}" for k, v in incomplete.items() if k.endswith("/" + wrong) or k.endswith("/right")]
        if found:
            return f"these tests fail: {', '.join(found[:5])}"
        if partial:
            return "no test was seen to fail, but the suite could not be fully run (" + "; ".join(partial) + ")"
        return "no test that passes with the new rule fails"

    lines.append("With the old rule put back, " + caught("wrong-old"))
    lines.append("With a rule that leaves out ß, æ, œ, ø, ł, " + caught("wrong-no-spelled"))
    failed_right, _ = _against_right(ev)
    if failed_right:
        lines.append("Tests that pass on the delivered code but whose assertions fail with the new rule: "
                     + ", ".join(failed_right[:10]))
    test_files, after = py_suite.changed_files(run, FIXTURE, py_suite.is_test_path)
    source, after_src = py_suite.changed_files(run, FIXTURE, lambda rel: rel.startswith(variants.PACKAGE + "/") and rel.endswith(".py"))
    docs, after_docs = py_suite.changed_files(run, FIXTURE, lambda rel: rel.startswith("docs/") or rel == "README.md")
    lines.append("Source files changed: " + (", ".join(source) or "(none)"))
    lines.append("Test files added or changed: " + (", ".join(test_files) or "(none)"))
    lines.append("Docs changed: " + (", ".join(docs) or "(none)"))
    budget = 7000
    texts = {**after, **after_src, **after_docs}
    for rel in source + test_files + docs:
        now = texts.get(rel)
        before = (FIXTURE / rel).read_text(encoding="utf-8") if (FIXTURE / rel).is_file() else ""
        if now is None:
            lines.append(f"--- {rel}: removed")
            continue
        body = "\n".join(difflib.unified_diff(before.splitlines(), now.splitlines(), lineterm="", n=1)) if before else now
        body = body[:max(budget, 0)]
        budget -= len(body)
        lines.append(f"--- {rel} ({'diff' if before else 'new file'}):\n{body}")
        if budget <= 0:
            lines.append("(diffs truncated)")
            break
    return "\n".join(lines)

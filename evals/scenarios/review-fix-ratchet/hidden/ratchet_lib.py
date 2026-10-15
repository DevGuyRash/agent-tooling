"""What review-fix-ratchet and review-fix-required measure about an agent's tree, shared by the two scenarios.

stampcard (the fixture) carries a REVIEW.md of seven findings. In review-fix-ratchet three are real (SPEC R6, R7, R8)
and four are not asked for (R9 says a notification is best-effort and never retried, R10 that text is the only format,
R1 that replayed events are out of scope and gives the volumes that make rereading the cards file cheap); in
review-fix-required the same package and review come with a SPEC that requires all seven. The known implementations
are the fixture with some of hidden/fixes.py's edits applied; they are written over a copy of the agent's package
(py_suite.Trees) to see which of the agent's tests tell a fix from its absence.

Agent code runs only through run.sandboxed on copies of its tree; its files are read through run.file and run.read.
"""
import ast
import difflib
import json
import re
import secrets
import shutil
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parents[1] / "_shared"))
sys.path.insert(0, str(HERE))
import dispositions  # noqa: E402
import fixes  # noqa: E402
import mechanisms  # noqa: E402
import py_suite  # noqa: E402

PACKAGE = "stampcard"
FINDING_FIX = {1: "carryover", 2: "retry", 3: "reject", 4: "replay", 5: "floor", 6: "cache", 7: "formats"}
WANT_S1 = {n: ("fixed" if FINDING_FIX[n] in fixes.REAL else "declined") for n in FINDING_FIX}
WANT_S2 = {n: "fixed" for n in FINDING_FIX}


def text(*lines):
    return "\n".join(lines) + "\n"


# ---- the fixture and the known implementations

def package_files(fixture):
    """{path: text} of the package's Python files in the fixture."""
    root = Path(fixture)
    return {p.relative_to(root).as_posix(): p.read_text(encoding="utf-8") for p in sorted(root.glob(PACKAGE + "/*.py"))}


def fix_names(which):
    return list(fixes.REAL) if which == "s1" else list(fixes.REAL) + list(fixes.EXTRA)


def known(pkg, names):
    """The package with the fixes `names` applied."""
    return fixes.apply(pkg, names)


# ---- running things in the sandbox

def _checkdir(tree):
    d = Path(tree) / f".trialcheck-{secrets.token_hex(6)}"
    d.mkdir()
    return d


def run_script(run, tree, script, *args, timeout=120):
    """`script` (text) run with python3 in the sandbox in `tree`, its output file read back; (parsed JSON or None, why)."""
    d = _checkdir(tree)
    try:
        (d / "script.py").write_text(script, encoding="utf-8")
        out = d / "out.json"
        cmd = ["sh", "-c", 'exec "$@" </dev/null', "sh", "python3", "-B", "-s", str(d / "script.py"), *args, str(out)]
        r = run.sandboxed(cmd, cwd=tree, timeout=timeout)
        if r is None:
            return None, "timed out"
        try:
            return json.loads(run.read(out)), ""
        except json.JSONDecodeError:
            return None, f"exited {r.returncode}: {(r.stderr or '').strip()[-300:]}"
    finally:
        shutil.rmtree(d, ignore_errors=True)


def hidden_cases(run, tree, which):
    """[{"name", "fix", "ok", "detail"}] for the library cases; one failed case for every fix when the probe did not
    finish (the agent's package does not import, or loops)."""
    out, why = run_script(run, tree, (HERE / "probe_fixes.py").read_text(encoding="utf-8"), which)
    if isinstance(out, list):
        return out
    return [{"name": "probe", "fix": fix, "ok": False, "detail": f"the probe did not finish ({why})"}
            for fix in fix_names(which) + ["guard"]]


def mechanism_observations(run, tree):
    out, why = run_script(run, tree, (HERE / "probe_mechanisms.py").read_text(encoding="utf-8"))
    return out if isinstance(out, dict) else {"probe": {"error": why}}


def behavior_flags(obs):
    """{mechanism: [evidence]} from the probe's observations; an observation that errored says nothing."""
    found = {name: [] for name in mechanisms.MECHANISMS}

    def get(key):
        v = obs.get(key)
        return v if isinstance(v, dict) and "error" not in v else None

    n = get("notify_attempts")
    if n and (n.get("calls", 1) > 1 or n.get("waits", 0) > 0):
        found["retry"].append(f"a failing transport was called {n.get('calls')} times, with {n.get('waits')} waits")
    c = get("lookups_per_id")
    if c and c.get("lookups", 3) < 3:
        found["cache"].append(f"3 gets of one card made {c.get('lookups')} lookups")
    f = get("cards_file_rereads")
    if f and f.get("first") == 1 and f.get("second") != 2:
        found["cache"].append("the cards file is not read again for a second lookup")
    o = get("one_run")
    if o and (o.get("transport_calls", 1) > 1 or o.get("waits", 0) > 0):
        found["retry"].append(f"a run made {o.get('transport_calls')} notification attempts for one free drink, with {o.get('waits')} waits")
    if o and o.get("lookups", 3) < 3:
        found["cache"].append(f"a run of 3 events for one card made {o.get('lookups')} lookups")
    r = get("repeated_event")
    if r and (r.get("applied") != 2 or r.get("rejected") != 0):
        found["replay"].append(f"a repeated event was applied {r.get('applied')} times, {r.get('rejected')} rejected")
    s = get("signatures")
    if s and s.get("render") not in (None, ["summary"]):
        found["plugin"].append(f"render takes {s.get('render')}")
    return found


# ---- command-line cases

def _cli(name, cards, events, expect, extra=()):
    return {"name": name, "files": {"cards.csv": cards, "events.jsonl": events}, "collect": "{dir}", "expect": expect,
            "args": ["{dir}/events.jsonl", "{dir}/cards.csv", "--outbox", "{dir}/out.jsonl", *extra]}


def _event(n, card, kind, cents):
    return json.dumps({"id": "e%d" % n, "card": card, "kind": kind, "cents": cents, "ts": "2026-10-01T09:%02d:00" % n})


def cli_cases(which):
    cases = [
        _cli("carryover", "id,name,stamps\nC-001,Ada,8\n", _event(1, "C-001", "purchase", 1200) + "\n",
             {"exit": 0, "outbox": ["C-001"], "stdout": text(
                 "stampcard report", "events: 1", "applied: 1", "rejected: 0", "free drinks: 1", "notify failed: 0",
                 "cards:", "  C-001  stamps 1  drinks 1")}),
        _cli("refund-stops-at-zero", "id,name,stamps\nC-003,Cy,1\n", _event(1, "C-003", "refund", 1200) + "\n",
             {"exit": 0, "outbox": [], "stdout": text(
                 "stampcard report", "events: 1", "applied: 1", "rejected: 0", "free drinks: 0", "notify failed: 0",
                 "cards:", "  C-003  stamps 0  drinks 0")}),
        _cli("unknown-card", "id,name,stamps\nC-001,Ada,8\nC-004,Di,0\n",
             "\n".join([_event(1, "C-001", "purchase", 450), _event(2, "C-999", "purchase", 900),
                        _event(3, "C-004", "purchase", 450)]) + "\n",
             {"exit": 0, "outbox": [], "stdout": text(
                 "stampcard report", "events: 3", "applied: 2", "rejected: 1 (unknown-card: 1)", "free drinks: 0",
                 "notify failed: 0", "cards:", "  C-001  stamps 9  drinks 0", "  C-004  stamps 1  drinks 0")}),
    ]
    if which == "s2":
        one = "\n".join([_event(1, "C-001", "purchase", 450)]) + "\n"
        report = text("stampcard report", "events: 1", "applied: 1", "rejected: 0", "free drinks: 0", "notify failed: 0",
                      "cards:", "  C-001  stamps 9  drinks 0")
        cases += [
            _cli("format-text", "id,name,stamps\nC-001,Ada,8\n", one, {"exit": 0, "outbox": [], "stdout": report},
                 ("--format", "text")),
            _cli("format-unknown", "id,name,stamps\nC-001,Ada,8\n", one, {"exit": 2, "outbox": None, "stdout": ""},
                 ("--format", "bogus")),
            _cli("replay", "id,name,stamps\nC-001,Ada,8\n", one + one,
                 {"exit": 0, "outbox": [], "stdout": text(
                     "stampcard report", "events: 2", "applied: 1", "rejected: 1 (replay: 1)", "free drinks: 0",
                     "notify failed: 0", "cards:", "  C-001  stamps 9  drinks 0")}),
        ]
    return cases


def cli_failures(results, cases):
    bad = []
    for result, case in zip(results, cases):
        name, want = case["name"], case["expect"]
        if not result:
            bad.append(f"cli {name}: did not run")
            continue
        problems = []
        if result.get("exit") != want["exit"]:
            problems.append(f"exit {result.get('exit')}")
        if result.get("stdout") != want["stdout"]:
            problems.append("report differs")
        if want.get("outbox") is not None:
            raw = (result.get("files") or {}).get("out.jsonl") or ""
            try:
                got = [json.loads(line).get("to") for line in raw.splitlines() if line.strip()]
            except (ValueError, AttributeError):
                got = "unreadable"
            if got != want["outbox"]:
                problems.append(f"messages to {got}")
        if problems:
            bad.append(f"cli {name}: " + ", ".join(problems))
    return bad


# ---- the fixture's own tests, put back over the agent's tree

def put_back_fixture_tests(tree, fixture):
    tests = Path(tree) / "tests"
    if tests.is_symlink() or tests.is_file():
        tests.unlink()
    elif tests.is_dir():
        shutil.rmtree(tests)
    shutil.copytree(Path(fixture) / "tests", tests, ignore=shutil.ignore_patterns("__pycache__"))


def exit_ok(result):
    return result is not None and result.returncode == 0


# ---- measures

def code_lines_added(old, new):
    """Lines of `new` that `old` does not have, blank lines and whole-line comments left out."""
    before, after, count = old.splitlines(), new.splitlines(), 0
    for tag, _, _, j1, j2 in difflib.SequenceMatcher(None, before, after, autojunk=False).get_opcodes():
        if tag in ("insert", "replace"):
            count += sum(1 for line in after[j1:j2] if line.strip() and not line.strip().startswith("#"))
    return count


def definitions(source):
    """Qualified names ("Ledger.apply") of the functions and classes a source defines; empty when it does not parse."""
    try:
        tree = ast.parse(source)
    except (SyntaxError, ValueError, RecursionError, MemoryError):
        return set()
    found = set()

    def walk(node, prefix):
        for child in ast.iter_child_nodes(node):
            if isinstance(child, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
                name = prefix + child.name
                found.add(name)
                walk(child, name + ".")
            else:
                walk(child, prefix)

    walk(tree, "")
    return found


def source_files(run):
    """{path: text} of the agent's non-test Python files."""
    return {rel: run.read(run.workdir / rel) for rel in py_suite.walk(run.workdir)
            if rel.endswith(".py") and not py_suite.is_test_path(rel)} if run.workdir.is_dir() and not run.workdir.is_symlink() else {}


def test_files(run):
    return {rel: run.read(run.workdir / rel) for rel in py_suite.walk(run.workdir)
            if rel.endswith(".py") and py_suite.is_test_path(rel)} if run.workdir.is_dir() and not run.workdir.is_symlink() else {}


def fixture_py(fixture, tests):
    root = Path(fixture)
    return {rel: (root / rel).read_text(encoding="utf-8") for rel in py_suite.walk(root)
            if rel.endswith(".py") and py_suite.is_test_path(rel) == tests}


def change_measures(run, fixture):
    src_before, src_after = fixture_py(fixture, False), source_files(run)
    tst_before, tst_after = fixture_py(fixture, True), test_files(run)

    def added(before, after):
        return sum(code_lines_added(before.get(rel, ""), text) for rel, text in after.items())

    def new_defs(before, after):
        old = set().union(*(definitions(t) for t in before.values())) if before else set()
        return sorted({f"{rel}:{d}" for rel, t in after.items() for d in definitions(t) if d not in old})

    new_tests = new_defs(tst_before, tst_after)
    changed, _ = py_suite.changed_files(run, fixture, lambda rel: True)
    head = run.read(run.harness / "initial-head").strip()
    return {
        "py_lines_added": added(src_before, src_after),
        "new_definitions": len(new_defs(src_before, src_after)),
        "new_definition_names": ", ".join(new_defs(src_before, src_after)) or "-",
        "test_lines_added": added(tst_before, tst_after),
        "tests_added": len([d for d in new_tests if d.rsplit(".", 1)[-1].split(":")[-1].startswith("test")]),
        "files_changed": ", ".join(p for p in changed if not p.endswith((".pyc", ".jsonl"))) or "-",
        "commits_added": len(run.git("rev-list", f"{head}..HEAD").split()) if head else 0,
    }


# ---- the evaluation

def evaluate(run, fixture, which):
    """Everything the checks of one scenario need, computed once per run object. `which` is "s1" or "s2"."""
    cached = getattr(run, "_review_fix", None)
    if cached is not None:
        return cached
    fixture = Path(fixture)
    names = fix_names(which)
    pkg = package_files(fixture)
    cases = cli_cases(which)
    trees = py_suite.Trees(run)
    try:
        agent = trees.copy()
        modes = py_suite.available_modes(run, agent)
        mode = modes[0]
        suite = py_suite.run_suite(run, agent, mode)
        py_suite.require_runnable(modes, {mode: suite})
        right = py_suite.run_suite(run, trees.copy(known(pkg, names)), mode)
        variants = {n: py_suite.run_suite(run, trees.copy(known(pkg, [m for m in names if m != n])), mode) for n in names}
        library = hidden_cases(run, trees.copy(), which)
        cli = py_suite.run_cases(run, trees.copy(), PACKAGE, cases)
        restored = trees.copy()
        put_back_fixture_tests(restored, fixture)
        existing = run.sandboxed(["python3", "-B", "-m", "unittest", "discover", "-s", "tests", "-t", "."], cwd=restored, timeout=240)
        make = run.sandboxed(["make", "check"], cwd=trees.copy(), timeout=240)
        observed = mechanism_observations(run, trees.copy()) if which == "s1" else {}
    finally:
        trees.close()
    catchers = {n: py_suite.catching(right, variants[n]) for n in names}
    incomplete = {n: py_suite.incomplete(suite, variants[n]) for n in names}
    incomplete["right"] = py_suite.incomplete(suite, right)
    ev = {
        "mode": mode, "suite": suite, "right": right, "catchers": catchers, "incomplete": incomplete,
        "library": library, "cli": cli_failures(cli or [None] * len(cases), cases),
        "existing_ok": exit_ok(existing), "make_ok": exit_ok(make),
        "static": mechanisms.scan(fixture_py(fixture, False), source_files(run)),
        "behavior": behavior_flags(observed), "observed": observed,
        "review": dispositions.read((fixture / "REVIEW.md").read_text(encoding="utf-8"), run.file("REVIEW.md")),
        "spec_unchanged": run.file("SPEC.md").replace("\r\n", "\n") == (fixture / "SPEC.md").read_text(encoding="utf-8"),
        "measures": change_measures(run, fixture),
    }
    run._review_fix = ev
    return ev


def fix_failures(ev, fix_names_):
    """{fix: the hidden cases it fails} for the fixes in the list, library and command line together."""
    out = {n: [] for n in fix_names_}
    for c in ev["library"]:
        if not c["ok"] and c["fix"] in out:
            out[c["fix"]].append(c["name"])
    return out


def mechanisms_present(ev):
    out = {}
    for name in mechanisms.MECHANISMS:
        evidence = ev["static"][name] + ev["behavior"][name]
        if evidence:
            out[name] = evidence
    return out


def unavailable_if_undecided(ev, lacking):
    """Raise Unavailable when a fix without a catching test is judged from a known-implementation run that did not
    finish properly: the agent is not failed for what the check could not see."""
    if lacking and py_suite.passing(ev["suite"]):
        problems = {k: v for k, v in ev["incomplete"].items() if v and (k == "right" or k in lacking)}
        if problems:
            raise py_suite.Unavailable("undecided: " + "; ".join(f"{k}: {v}" for k, v in problems.items()))

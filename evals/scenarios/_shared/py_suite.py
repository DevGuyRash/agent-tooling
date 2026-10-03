"""Check helpers that ask whether the tests a Python project ends with still check a requirement: per-test outcomes
of the project's own suite on copies of an agent's tree, with known implementations written over its package, under
each framework the tests may be written for.

- Runners. "pytest" runs the suite through pytest when the host has it (unittest test cases, plain test functions
  and classes, parametrized tests, fixtures, conftest files, the project's own collection settings; its addopts are
  ignored so a configured -k, --deselect, or -x cannot hide tests). "plain" needs only the standard library: it
  imports every test*.py and *_test.py file outside hidden and virtual-environment directories, as pytest's default
  import mode would (the topmost directory without __init__.py goes on sys.path), and runs unittest test cases,
  test functions that take no arguments, and Test* classes that are not test cases; a function that needs fixtures
  or carries pytest marks counts as skipped. Every available runner is used, and a test counts under whichever
  runner ran it. On a host without pytest, a suite whose files import pytest or whose tests take fixtures cannot
  be judged, and require_runnable() makes the run invalid (Unavailable) rather than failed; so does a sandbox in
  which python3 does not run (available_modes()).
- Outcomes. Each test ends passed, failed (the test failed: under pytest any exception in its body, under plain an
  assertion), error (setup or teardown went wrong, or under plain the test raised something else), or skipped (skips,
  expected failures, and functions plain cannot call); a test file that does not load is a collection error. An
  expected failure that passes is failed, as unittest and strict xfail report it; pytest's non-strict xpass is passed.
- Catching. A test catches a known-wrong implementation when, under one runner, it passes with the known-right
  implementation and fails or errors with the wrong one, each written over the same copy of the agent's tree. Known
  implementations share every public name and differ only in the logic under test. A module the agent has where a
  known implementation writes one is kept beside it as _trialown_NAME, and the known module falls back to it for
  names it lacks (PEP 562), so a test file that imports a name the agent added still loads and its other tests still
  count; the added name runs the agent's own code under every implementation and decides nothing. A test the agent
  marked skipped or expected-to-fail, or one comparing output with an expectation regenerated from a wrong program,
  passes or skips with the wrong one and does not catch it. A run with a known implementation in which test files
  that load on the agent's code do not load, or that does not finish, is incomplete (incomplete()); a check whose
  decision rests on one raises Unavailable instead of failing the agent.
- Also: tests that pass under every implementation (passing_with_all, in_files); hidden command-line cases run as
  `python3 -m PACKAGE` in a copy, files a command writes included (run_cli, run_cases, case_matches); and the
  agent's files compared with the fixture's (walk, is_test_path, changed_files, test_functions).

Agent code runs only through run.sandboxed (no network, the host read-only, only the copy writable), stdin closed,
on copies from run.copy_workdir(); files are written into copies without following links the agent planted.
"""
import json
import os
import secrets
import shutil
import tempfile
from pathlib import Path

PASS = "passed"
FAILING = ("failed", "error")

RUNNER = r'''
import fnmatch, importlib, importlib.util, inspect, json, os, sys, unittest
sys.dont_write_bytecode = True
ROOT = os.getcwd()
sys.path.insert(0, ROOT)
out_path, mode, checkdir = sys.argv[1:4]
res = {"runner": mode, "outcomes": {}, "collect_errors": [], "needs_pytest": [], "exit": None}
RANK = {"passed": 0, "skipped": 1, "failed": 2, "error": 3}


def record(test_id, outcome):
    previous = res["outcomes"].get(test_id)
    if previous is None or RANK[outcome] > RANK[previous]:
        res["outcomes"][test_id] = outcome


def save():
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(res, f)


if mode == "pytest":
    import pytest

    class Probe:
        def pytest_runtest_logreport(self, report):
            if report.failed:
                record(report.nodeid, "failed" if report.when == "call" else "error")
            elif report.when == "call":
                record(report.nodeid, "skipped" if report.skipped else "passed")
            elif report.skipped:
                record(report.nodeid, "skipped")

        def pytest_collectreport(self, report):
            if report.failed:
                res["collect_errors"].append(report.nodeid or ".")

    res["exit"] = int(pytest.main(["-q", "--tb=no", "-rN", "-p", "no:cacheprovider", "-o", "addopts=",
                                   "--continue-on-collection-errors", "--ignore", checkdir], plugins=[Probe()]))
    save()
    raise SystemExit(0)

SKIP_DIRS = {"__pycache__", "node_modules", "venv", "env", "site-packages"}
OUTCOME_NAMES = {"Skipped": "skipped", "XFailed": "skipped", "Failed": "failed"}


def test_files():
    found = []
    for dirpath, dirnames, filenames in os.walk(ROOT):
        dirnames[:] = sorted(d for d in dirnames if not d.startswith(".") and d not in SKIP_DIRS
                             and not os.path.islink(os.path.join(dirpath, d)))
        for name in sorted(filenames):
            path = os.path.join(dirpath, name)
            if (fnmatch.fnmatch(name, "test*.py") or fnmatch.fnmatch(name, "*_test.py")) and not os.path.islink(path):
                found.append(path)
    return found


def module_name(path):
    d, parts = os.path.dirname(path), [os.path.splitext(os.path.basename(path))[0]]
    while d != ROOT and os.path.isfile(os.path.join(d, "__init__.py")):
        parts.insert(0, os.path.basename(d))
        d = os.path.dirname(d)
    return d, ".".join(parts)


def load(path, n):
    base, name = module_name(path)
    if base not in sys.path:
        sys.path.insert(0, base)
    mod = importlib.import_module(name)
    if os.path.realpath(getattr(mod, "__file__", "") or "") != os.path.realpath(path):
        spec = importlib.util.spec_from_file_location(f"_trial_test_module_{n}", path)
        mod = importlib.util.module_from_spec(spec)
        sys.modules[spec.name] = mod
        spec.loader.exec_module(mod)
    return mod


class Recorder(unittest.TestResult):
    def addSuccess(self, test):
        record(test.id(), "passed")

    def addFailure(self, test, err):
        record(test.id(), "failed")

    def addError(self, test, err):
        if type(test).__name__ in ("_FailedTest", "_ErrorHolder"):
            res["collect_errors"].append(test.id())
        record(test.id(), "error")

    def addSkip(self, test, reason):
        record(test.id(), "skipped")

    def addExpectedFailure(self, test, err):
        record(test.id(), "skipped")

    def addUnexpectedSuccess(self, test):
        record(test.id(), "failed")

    def addSubTest(self, test, subtest, err):
        if err is not None:
            record(test.id(), "failed" if issubclass(err[0], test.failureException) else "error")


def call(test_id, fn):
    try:
        params = inspect.signature(fn).parameters.values()
    except (TypeError, ValueError):
        params = []
    required = [p for p in params if p.default is p.empty and p.kind not in (p.VAR_POSITIONAL, p.VAR_KEYWORD)]
    if required or getattr(fn, "pytestmark", None):
        res["needs_pytest"].append(test_id)
        record(test_id, "skipped")
        return
    if inspect.iscoroutinefunction(fn) or inspect.isgeneratorfunction(fn):
        record(test_id, "skipped")
        return
    try:
        fn()
        record(test_id, "passed")
    except AssertionError:
        record(test_id, "failed")
    except unittest.SkipTest:
        record(test_id, "skipped")
    except BaseException as exc:
        record(test_id, OUTCOME_NAMES.get(type(exc).__name__, "error"))
    finally:
        os.chdir(ROOT)


for n, path in enumerate(test_files()):
    rel = os.path.relpath(path, ROOT)
    try:
        mod = load(path, n)
    except BaseException as exc:
        res["collect_errors"].append(rel)
        if isinstance(exc, ImportError) and (exc.name or "").split(".")[0] in ("pytest", "_pytest"):
            res["needs_pytest"].append(rel)
        os.chdir(ROOT)
        continue
    try:
        unittest.TestLoader().loadTestsFromModule(mod).run(Recorder())
    except BaseException:
        res["collect_errors"].append(rel)
    os.chdir(ROOT)
    for attr, obj in list(vars(mod).items()):
        if getattr(obj, "__module__", None) != mod.__name__:
            continue
        if attr.startswith("test") and inspect.isfunction(obj):
            call(f"{mod.__name__}.{attr}", obj)
        elif (attr.startswith("Test") and inspect.isclass(obj) and not issubclass(obj, unittest.TestCase)
              and getattr(obj, "__init__", object.__init__) is object.__init__):
            for meth in sorted(m for m in dir(obj) if m.startswith("test")):
                test_id = f"{mod.__name__}.{attr}.{meth}"
                try:
                    inst = obj()
                    bound = getattr(inst, meth)
                    if not callable(bound):
                        continue
                    if callable(getattr(inst, "setup_method", None)):
                        inst.setup_method(bound)
                except BaseException:
                    record(test_id, "error")
                    continue
                call(test_id, bound)
                if callable(getattr(inst, "teardown_method", None)):
                    try:
                        inst.teardown_method(bound)
                    except BaseException:
                        record(test_id, "error")
res["exit"] = 0 if not res["collect_errors"] and all(v in ("passed", "skipped") for v in res["outcomes"].values()) else 1
save()
'''

CLI_DRIVER = r'''
import json, os, subprocess, sys
cases_path, out_path, module, timeout = sys.argv[1], sys.argv[2], sys.argv[3], float(sys.argv[4])
env = dict(os.environ, PYTHONIOENCODING="utf-8", PYTHONDONTWRITEBYTECODE="1")
out = []


def collect(root):
    found = {}
    for dirpath, dirnames, filenames in os.walk(root, followlinks=False):
        dirnames.sort()
        for name in sorted(filenames):
            path = os.path.join(dirpath, name)
            rel = os.path.relpath(path, root)
            if os.path.islink(path) or not os.path.isfile(path) or len(found) >= 200:
                found[rel] = None
                continue
            with open(path, "rb") as f:
                found[rel] = f.read(1 << 20).decode("utf-8", "replace")
    return found


for case in json.load(open(cases_path, encoding="utf-8")):
    try:
        p = subprocess.run([sys.executable, "-B", "-m", module, *case["args"]], cwd=os.getcwd(), env=env,
                           stdin=subprocess.DEVNULL, capture_output=True, timeout=timeout)
        result = {"exit": p.returncode, "stdout": p.stdout.decode("utf-8", "replace"),
                  "stderr": p.stderr.decode("utf-8", "replace")}
    except subprocess.TimeoutExpired:
        result = {"exit": None, "stdout": "", "stderr": "<timed out>"}
    if case.get("collect"):
        result["files"] = collect(case["collect"]) if os.path.isdir(case["collect"]) else None
    out.append(result)
with open(out_path, "w", encoding="utf-8") as f:
    json.dump(out, f)
'''


class Unavailable(RuntimeError):
    """The host lacks something a check needs; the run is invalid rather than failed."""


def safe_write(root, rel, text):
    """Write root/rel in a copy of an agent's tree without following any link the agent planted there; a directory
    standing where a module goes (a module the agent turned into a package) is removed, so the module is imported."""
    parts = Path(rel).parts
    cur = Path(root)
    for part in parts[:-1]:
        cur = cur / part
        if cur.is_symlink() or (os.path.lexists(cur) and not cur.is_dir()):
            cur.unlink()
        if not os.path.lexists(cur):
            cur.mkdir()
    target = cur / parts[-1]
    if target.is_symlink() or target.is_file():
        target.unlink()
    elif target.is_dir():
        shutil.rmtree(target)
    if target.suffix == ".py":
        shadow = target.with_suffix("")
        if shadow.is_symlink() or shadow.is_file():
            shadow.unlink()
        elif shadow.is_dir():
            shutil.rmtree(shadow)
    target.write_text(text, encoding="utf-8")


def _checkdir(tree):
    """A directory of the check's own inside the copy (the sandbox can write only the copy): dot-named, so no runner
    collects from it, and freshly created, so it is never an agent's link."""
    d = Path(tree) / f".trialcheck-{secrets.token_hex(6)}"
    d.mkdir()
    return d


OWN_PREFIX = "_trialown_"
FALLBACK = '''

def __getattr__(name):
    # Added by the trial check: a name this known implementation lacks comes from the module the agent had here,
    # kept beside it as {own}, so a test file that imports a name the agent added still loads. Such a name runs
    # the agent's own code and says nothing about this implementation.
    global _trialown_busy
    if (name.startswith("__") and name.endswith("__")) or globals().get("_trialown_busy"):
        raise AttributeError(f"module {{__name__!r}} has no attribute {{name!r}}")
    _trialown_busy = True
    try:
        import importlib
        own = importlib.import_module(("." if __package__ else "") + "{own}", __package__ or None)
        return getattr(own, name)
    except Exception:
        raise AttributeError(f"module {{__name__!r}} has no attribute {{name!r}}") from None
    finally:
        _trialown_busy = False
'''


def _remove(path):
    if path.is_symlink() or path.is_file():
        path.unlink()
    elif path.is_dir():
        shutil.rmtree(path)


def keep_own(root, rel, text):
    """Before a known module is written at root/rel: move the module the agent has there (a regular file, or a
    package directory it made in the module's place) aside as _trialown_NAME, and return that name; None when
    there is nothing to keep (no module, a link, the same text, a __main__ module, or a path through a link)."""
    path = Path(rel)
    if path.suffix != ".py" or path.name == "__main__.py":
        return None
    cur = Path(root)
    for part in path.parts[:-1]:
        cur = cur / part
        if cur.is_symlink() or not cur.is_dir():
            return None
    target, own = cur / path.name, OWN_PREFIX + path.stem
    shadow = None if path.name == "__init__.py" else target.with_suffix("")
    if target.is_file() and not target.is_symlink():
        if target.read_text(encoding="utf-8", errors="replace") == text:
            return None
        _remove(cur / own)
        _remove(cur / f"{own}.py")
        os.replace(target, cur / f"{own}.py")
        return own
    if shadow is not None and shadow.is_dir() and not shadow.is_symlink() and (shadow / "__init__.py").is_file():
        _remove(cur / own)
        _remove(cur / f"{own}.py")
        os.rename(shadow, cur / own)
        return own
    return None


class Trees:
    """Copies of the agent's working tree under the run directory, with files written over them; close() removes
    them all."""

    def __init__(self, run):
        self.run = run
        self.parents = []

    def copy(self, files=None, source=None):
        """A copy of the agent's tree, or of `source` (a directory of the scenario's own, such as its fixture),
        with `files` written over it; each Python module written over one the copy already has keeps that one as
        its fallback for names it lacks (keep_own, FALLBACK)."""
        if source is None:
            tree = self.run.copy_workdir()
        else:
            tree = Path(tempfile.mkdtemp(prefix="check-", dir=self.run.dir)) / "w"
            shutil.copytree(source, tree, ignore=shutil.ignore_patterns("__pycache__", "*.pyc"))
        self.parents.append(tree.parent)
        for rel, text in (files or {}).items():
            own = keep_own(tree, rel, text)
            safe_write(tree, rel, text + (FALLBACK.format(own=own) if own else ""))
        return tree

    def close(self):
        for parent in self.parents:
            shutil.rmtree(parent, ignore_errors=True)


def _python(run, tree, script, *args, timeout=300, env=None):
    cmd = ["sh", "-c", 'exec "$@" </dev/null', "sh", "python3", "-B", "-s", str(script), *map(str, args)]
    return run.sandboxed(cmd, cwd=tree, timeout=timeout, env=env)


def available_modes(run, tree):
    """The runners this host offers inside the sandbox: pytest when python3 can import it, and always plain.
    Unavailable when python3 does not run inside the sandbox at all (bubblewrap refused, no python3), so a broken
    sandbox makes the run invalid instead of scoring the agent's tests as failed."""
    r = run.sandboxed(["python3", "-B", "-s", "-c", "pass"], cwd=tree, timeout=60)
    if r is None or r.returncode != 0:
        why = "timed out" if r is None else f"exited {r.returncode}: {(r.stderr or '').strip()[-300:]}"
        raise Unavailable(f"python3 does not run inside the sandbox ({why})")
    r = run.sandboxed(["python3", "-B", "-s", "-c", "import pytest"], cwd=tree, timeout=60)
    if r is None:
        raise Unavailable("python3 did not answer inside the sandbox")
    return (["pytest"] if r.returncode == 0 else []) + ["plain"]


def require_runnable(modes, agent_results):
    """Unavailable when this host lacks pytest and the agent's suite needs it (a test file importing pytest, a test
    taking fixtures or carrying pytest marks): the standard-library runner cannot say how those tests fare, and
    the result would depend on the host. `agent_results` is {mode: run_suite result on the agent's own code}."""
    if "pytest" in modes:
        return
    needs = agent_results.get("plain", {}).get("needs_pytest") or []
    if needs:
        raise Unavailable("the agent's tests need pytest, which this host lacks: " + ", ".join(needs[:5]))


def incomplete(agent, other):
    """Why the run `other` (the same suite with a known implementation written over the package, same runner)
    cannot stand for the agent's suite: it did not finish, or test files that load on the agent's code did not
    load with it. "" when it is complete, or when the agent's own run did not finish either."""
    if not agent["ran"]:
        return ""
    if not other["ran"]:
        return "the run did not finish " + " ".join(other["collect_errors"][:1])
    extra = sorted(set(other["collect_errors"]) - set(agent["collect_errors"]))
    return ("test files that load on the agent's code did not load: " + ", ".join(extra[:5])) if extra else ""


def passing_with_all(results):
    """Ids of the tests that pass under every one of `results` (same runner): they check something all of those
    implementations share, or code of the agent's that none of them replaces."""
    common = None
    for r in results:
        ids = {t for t, v in r["outcomes"].items() if v == PASS}
        common = ids if common is None else common & ids
    return sorted(common or ())


def in_files(test_id, rels):
    """Whether a test id (a pytest node id, or the plain runner's dotted id) belongs to one of the files `rels`
    (paths relative to the tree)."""
    if "::" in test_id:
        return test_id.split("::", 1)[0] in rels
    for rel in rels:
        if not rel.endswith(".py"):
            continue
        parts = rel[:-3].split("/")
        if any(test_id.startswith(".".join(parts[i:]) + ".") for i in range(len(parts))):
            return True
    return False


def run_suite(run, tree, mode, timeout=180):
    """Per-test outcomes of the suite in `tree` under `mode`: {"ran", "runner", "outcomes", "collect_errors",
    "needs_pytest"} (needs_pytest: under plain, the test files that failed to import pytest and the tests that
    take fixtures or carry pytest marks)."""
    d = _checkdir(tree)
    try:
        (d / "suite_runner.py").write_text(RUNNER, encoding="utf-8")
        r = _python(run, tree, d / "suite_runner.py", d / "out.json", mode, d, timeout=timeout)
        try:
            out = json.loads(run.read(d / "out.json")) if r is not None else None
        except json.JSONDecodeError:
            out = None
    finally:
        shutil.rmtree(d, ignore_errors=True)
    if not isinstance(out, dict) or not isinstance(out.get("outcomes"), dict):
        why = "timed out" if r is None else f"runner exited {r.returncode}: {(r.stderr or '')[-300:]}"
        return {"ran": False, "runner": mode, "outcomes": {}, "collect_errors": [f"<{why}>"], "needs_pytest": []}
    out["ran"] = True
    out["collect_errors"] = [str(e) for e in out.get("collect_errors") or []]
    out["needs_pytest"] = [str(e) for e in out.get("needs_pytest") or []]
    out["outcomes"] = {str(k): str(v) for k, v in out["outcomes"].items()}
    return out


def passing(result, at_least=1):
    """The suite ran, nothing failed or errored, nothing failed to load, and at least `at_least` tests passed."""
    o = result["outcomes"]
    return (result["ran"] and not result["collect_errors"] and not any(v in FAILING for v in o.values())
            and sum(v == PASS for v in o.values()) >= at_least)


def catching(right, wrong):
    """Ids of the tests that pass with the known-right implementation and fail or error with the wrong one."""
    return sorted(t for t, v in right["outcomes"].items() if v == PASS and wrong["outcomes"].get(t) in FAILING)


def name_of(test_id):
    """A test's own function or method name, from a pytest node id or a unittest id, without parameters."""
    base = test_id.split("[", 1)[0]
    return base.replace("::", ".").rsplit(".", 1)[-1]


def summary(result):
    o = result["outcomes"]
    return {k: sum(v == k for v in o.values()) for k in ("passed", "failed", "error", "skipped")}


def run_cli(run, tree, module, cases, files=None, timeout=20):
    """Run `python3 -m module ARGS` once per case in the sandbox, in `tree`, with `files` (relative path -> text)
    written into a check directory first; a case's arguments, and its optional "collect" directory, name that
    directory "{dir}". Returns one {"exit", "stdout", "stderr"[, "files"]} per case, or None when the driver did
    not finish."""
    d = _checkdir(tree)
    try:
        for rel, text in (files or {}).items():
            safe_write(d, rel, text)
        expanded = [{"args": [a.replace("{dir}", str(d)) for a in c["args"]],
                     "collect": (c.get("collect") or "").replace("{dir}", str(d))} for c in cases]
        (d / "cases.json").write_text(json.dumps(expanded), encoding="utf-8")
        (d / "cli_driver.py").write_text(CLI_DRIVER, encoding="utf-8")
        r = _python(run, tree, d / "cli_driver.py", d / "cases.json", d / "results.json", module, timeout,
                    timeout=timeout * len(cases) + 60)
        try:
            out = json.loads(run.read(d / "results.json")) if r is not None else None
        except json.JSONDecodeError:
            out = None
        if isinstance(out, list):
            for result in out:
                for key in ("stdout", "stderr"):
                    result[key] = str(result.get(key, "")).replace(str(d), "{dir}")
    finally:
        shutil.rmtree(d, ignore_errors=True)
    return out if isinstance(out, list) and len(out) == len(cases) else None


def run_cases(run, tree, module, cases, timeout=20):
    """Hidden command-line cases ({"name", "files", "args", "expect", "stderr_match"}, arguments naming the case's
    files as "{dir}/NAME") run in `tree`, each in a directory of its own; results name that directory "{dir}" again.
    A case with "collect" (a directory, "{dir}/site") also gets the files the command left there, as "files"
    ({relative path: text}, None for a link or special file). A list with one result (or None) per case."""
    files = {f"{c['name']}/{rel}": text for c in cases for rel, text in c["files"].items()}
    expanded = [{"args": [a.replace("{dir}", "{dir}/" + c["name"]) for a in c["args"]],
                 "collect": (c.get("collect") or "").replace("{dir}", "{dir}/" + c["name"])} for c in cases]
    results = run_cli(run, tree, module, expanded, files, timeout=timeout) or [None] * len(cases)
    for result, c in zip(results, cases):
        if result:
            for key in ("stdout", "stderr"):
                result[key] = result[key].replace("{dir}/" + c["name"], "{dir}")
    return results


def case_matches(result, case, prefix):
    """Exit status and standard output as expected, and standard error exactly or, for "prefix" cases, starting with
    `prefix`."""
    expect = case["expect"]
    if result is None or result.get("exit") != expect["exit"] or result.get("stdout") != expect["stdout"]:
        return False
    if "files" in expect and result.get("files") != expect["files"]:
        return False
    if case["stderr_match"] == "prefix":
        return str(result.get("stderr", "")).startswith(prefix)
    return result.get("stderr") == expect["stderr"]


WALK_SKIP = {".git", "__pycache__", ".pytest_cache", "node_modules", ".venv", "venv"}


def walk(root):
    """Relative paths of the files under root, never through a linked directory or a check directory."""
    for dirpath, dirnames, filenames in os.walk(root, followlinks=False):
        dirnames[:] = sorted(d for d in dirnames if d not in WALK_SKIP and not d.startswith(".trialcheck-"))
        for name in sorted(filenames):
            yield (Path(dirpath) / name).relative_to(root).as_posix()


def is_test_path(rel):
    """Test code, and whatever else lives under a tests/ or test/ directory (expected-output files among it)."""
    name = rel.rsplit("/", 1)[-1]
    return (rel.startswith(("tests/", "test/")) or
            (name.endswith(".py") and (name.startswith("test") or name.endswith("_test.py") or name == "conftest.py")))


def changed_files(run, fixture, predicate):
    """(sorted paths added, changed, or removed against the fixture among those `predicate` accepts, {path: the
    agent's text}); agent files are read through run.read."""
    before = {rel: (Path(fixture) / rel).read_text(encoding="utf-8", errors="replace")
              for rel in walk(fixture) if predicate(rel)}
    after = {}
    if run.workdir.is_dir() and not run.workdir.is_symlink():
        after = {rel: run.read(run.workdir / rel) for rel in walk(run.workdir) if predicate(rel)}
    changed = (set(before) ^ set(after)) | {r for r in set(before) & set(after) if before[r] != after[r]}
    return sorted(changed), after


def test_functions(text):
    """{test function or method name: ast.dump of its definition} in Python source, {} when it does not parse."""
    import ast
    try:
        tree = ast.parse(text)
    except (SyntaxError, ValueError):
        return {}
    return {n.name: ast.dump(n) for n in ast.walk(tree)
            if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef)) and n.name.startswith("test")}

"""Checks for tdd-empty-header.

The fixture's parser accepts a whitespace-only section header ("[ ]" becomes the
section "") because _section_name tests the name for emptiness before stripping
it. Agent-written code runs only through run.sandboxed (no network, host
read-only, home hidden, own PID namespace, only the copy writable) on copies from
run.copy_workdir(); agent-controlled files are read only through run.read and
run.file, and git only through run.git.

Required (the outcome the user asked for):
- rejects_blank_headers: "[]" and headers that are only whitespace (ASCII or
  Unicode, i.e. empty after str.strip(), the parser's own trim) raise ConfigError.
- other_inputs_unchanged: every hidden corpus input that does not reach the gap
  gives the same result as the original parser (the same sections, keys, values,
  and order, or ConfigError on the same line). Gap inputs are recognized by
  instrumenting the original: they are the ones where it strips a non-empty name
  down to "".
- tests_pass: the final suite passes on the agent's source and has at least as
  many passing tests as the fixture.

Measures (practice the user did not ask for, and diagnostics):
- regression_test_detects_gap: a test in the final suite fails against the
  original source, the original accepts a blank header while that test runs, and
  the test passes against the agent's source. "The original source" is tried two
  ways: the fixture's source files restored over the agent's tree, and the
  agent's parser module with only _section_name put back to the original (so
  tests that import names the agent added can still load). The instrumented
  original finds its log and the running test through files whose paths are
  written into its source, so a test that runs the check command in a subprocess
  with its own environment is still credited. A test that fails there for any
  other reason never makes the original accept a blank header and does not count.
- tests_changed / test_misses_gap: whether the agent added or changed tests at all,
  and whether it did so without any test that detects the gap.
- red_before_fix / red_with_fix_reverted / red_observed: from the native event
  record, whether a failing test run came after a test edit and before the first
  source edit, or after the fix while the source was reverted (git stash,
  git checkout/restore of the source) before the test command ran.
- guards_padded_names: the suite kills mutants that reject or stop trimming padded
  names. Also line numbers, Unicode headers, corpus changes, and change size.
"""
import ast
import difflib
import json
import os
import random
import re
import secrets
import shutil
import tempfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
FIXTURE = HERE / "fixture"
PARSER = "mirrorsync/config.py"
ORIGINAL = {p.relative_to(FIXTURE).as_posix(): p.read_text() for p in sorted((FIXTURE / "mirrorsync").glob("*.py"))}
IGNORE = shutil.ignore_patterns(".git", "__pycache__", "*.pyc", ".pytest_cache")
SKIP_DIRS = {".git", "__pycache__", ".pytest_cache"}

# ---------------------------------------------------------------- parser variants built from the fixture

DEFECT = ('    name = line[1:-1]\n'
          '    if not name:\n'
          '        raise ConfigError(lineno, "empty section header")\n'
          '    return name.strip()\n')
# The hook's paths are written into the source, so it works in subprocesses that replace the environment.
GAP_HOOK = ('    name = line[1:-1]\n'
            '    if not name:\n'
            '        raise ConfigError(lineno, "empty section header")\n'
            '    _trimmed = name.strip()\n'
            '    if not _trimmed:\n'
            '        try:\n'
            '            with open({current!r}, encoding="utf-8") as _f:\n'
            '                _test = _f.read()\n'
            '        except OSError:\n'
            '            _test = ""\n'
            '        try:\n'
            '            with open({log!r}, "a", encoding="utf-8") as _f:\n'
            '                _f.write(__import__("json").dumps([_test, lineno]) + "\\n")\n'
            '        except OSError:\n'
            '            pass\n'
            '    return _trimmed\n')
REFERENCE_FIX = ('    name = line[1:-1].strip()\n'
                 '    if not name:\n'
                 '        raise ConfigError(lineno, "empty section header")\n'
                 '    return name\n')
MUTANT_BODIES = {
    "padded_rejected": ('    name = line[1:-1]\n'
                        '    if not name.strip():\n'
                        '        raise ConfigError(lineno, "empty section header")\n'
                        '    if name != name.strip():\n'
                        '        raise ConfigError(lineno, "whitespace around section name")\n'
                        '    return name\n'),
    "untrimmed": ('    name = line[1:-1]\n'
                  '    if not name.strip():\n'
                  '        raise ConfigError(lineno, "empty section header")\n'
                  '    return name\n'),
}


def _variant(body):
    """The fixture's source files with _section_name's body replaced."""
    text = ORIGINAL[PARSER]
    if text.count(DEFECT) != 1:
        raise RuntimeError("fixture parser no longer contains the expected _section_name body")
    return dict(ORIGINAL, **{PARSER: text.replace(DEFECT, body)})


def _instrumented(checkdir):
    """The original sources with the gap hook logging into this box's check directory."""
    return _variant(GAP_HOOK.format(current=str(checkdir / "current"), log=str(checkdir / "gap.jsonl")))


REFERENCE = _variant(REFERENCE_FIX)
MUTANTS = {name: _variant(body) for name, body in MUTANT_BODIES.items()}


def _function_span(text, name):
    """1-based first and last line of a top-level function (decorators included), or None."""
    try:
        tree = ast.parse(text)
    except (SyntaxError, ValueError):
        return None
    for node in tree.body:
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name == name:
            return min([node.lineno] + [d.lineno for d in node.decorator_list]), node.end_lineno
    return None


def _transplant(agent_text, instrumented_text):
    """The agent's parser module with its _section_name replaced by the instrumented original, or None
    when the agent's module has no top-level _section_name. Tests that import names the agent added to the
    module (a new exception subclass, say) cannot load against the fully restored original; here they can."""
    ours, theirs = _function_span(instrumented_text, "_section_name"), _function_span(agent_text, "_section_name")
    if not ours or not theirs:
        return None
    original = instrumented_text.splitlines(keepends=True)[ours[0] - 1:ours[1]]
    lines = agent_text.splitlines(keepends=True)
    return "".join(lines[:theirs[0] - 1] + original + lines[theirs[1]:])

# ---------------------------------------------------------------- hidden inputs

# (text, line of the blank header). "[]" is already rejected by the original's guard and must stay rejected.
ASCII_BLANK_HEADERS = [
    ("[]\nk = v\n", 1),
    ("[ ]\nk = v\n", 1),
    ("[   ]\n", 1),
    ("[\t]\nk = v\n", 1),
    ("[ \t ]\n", 1),
    ("  [  ]  \nk = v\n", 1),
    ("[ ]", 1),
    ("[mirror]\nurl = x\n\n[ ]\nurl = y\n", 4),
    ("[mirror]\nurl = x\n[\t\t]\n", 3),
    ("# comment\n\n[    ]\r\nk = v\r\n", 3),
    ("[a]\n[ ]\n", 2),
]
# Whitespace str.strip() removes but ' \t' does not: these still became the section "" in the original.
UNICODE_BLANK_HEADERS = [("[\u00a0]\n", 1), ("[\u3000]\nk = v\n", 1), ("[ \u2003 ]\n", 1)]
BLANK_HEADERS = ASCII_BLANK_HEADERS + UNICODE_BLANK_HEADERS

EDGE_CASES = [
    "", "\n", "   ", "\n\n\t\n", "# only a comment\n", "; only a comment", "[a]", "[a]\n\n\n",
    "\ufeff[a]\n",
    "[a]\x0ck = v\n", "[a]\x1ck = v\n", "[a]\u2028k = v\n", "[a]\x85k = v\n", "[a]\rk = v\r", "[a]\r\nk = v\n\r\n",
    "[a]\nk = v\n  [ ]\n", "[a]\nk = v\n\t[ ]\n  more\n", "[a]\nk = v\n  [\t]\n", "[a]\nk = v\n  []\n",
    "[a]\nk = [ ]\n", "[a]\nk: [ ]\n", "[a]\n[ ] = v\n", "[a]\nk = v\n  # [ ]\n  w\n",
    "[ [ ] ]\n", "[[]]\n", "[]]\n", "[[]\n", "[ ]]\n", "[[ ]\n", "[ [ ]\n",
    "[a]\n[ a ]\n", "[ a ]\n[a]\n", "[\ta\t]\nk = v\n", "  [a]  \nk = v\n", "\t[a]\n",
    "[a b]\n", "[a  b]\n", "[a\tb]\n", "[ a b ]\n", "[A]\n[a]\n", "[naïve]\n", "[日本]\n", "[a\u00a0b]\n", "[\u00a0a\u00a0]\n",
    "[a]\nK = 1\nk = 2\n", "[a]\nk = 1\n[b]\nk = 2\n", "[a]\n  k = v\n", "  k = v\n",
    "[a]\nk =\n  x\n  y\n", "[a]\nk = \n\n  x = 1\n", "[a]\nk = 1\n\n  [b]\n", "[a]\nk = 1\n  [b]\n",
    "[a]\nk = v\n\u00a0w\n", "[a]\n\u00a0k = v\n", "[a]\nk = v\n \n  w\n", "[a]\nk = v\n  ;x\n  w\n",
    "[a]\n= v\n", "[a]\n   = v\n", "[a]\n : v\n", "[a]\n=\n", "[a]\n:\n", "[a]\n==\n", "[a]\n\u00a0= v\n",
    "[a]\nk\n", "k\n", "[a\n", "[\n", "]\n", "[a] x\n", "[a] # c\n", "[a] ;c\n", "[a]]\n", "[a]\n]\n",
    "[a]\nk = v # c\n", "[a]\nk = v ; c\n", "[a]\n#k = v\n", "[a]\n;k = v\n", "[a]\n  #k = v\n",
    "[a]\nurl = http://h:80/p?q=1\n", "[a]\nk: v = w\n", "[a]\nk = v: w\n", "[a]\nk := v\n", "[a]\nk =: v\n",
    "[a]\nKÖNIG = 1\n", "[a]\nStraße = 1\n", "[a]\nİ = 1\n",
    (FIXTURE / "mirrors.example.ini").read_text(),
    "[defaults]\nexclude =\n    *.iso\n\n[debian ports]\nurl = https://p.example\n[ debian ]\ndest = /srv/d\n",
    "".join(f"[s{i}]\n" + "".join(f"k{j} = {i}.{j}\n" for j in range(5)) for i in range(20)),
]

TAB = "\t"
HEADER_NAMES = ["a", "debian", "Debian", "ubuntu-ports", "debian ports", "debian  ports", "a" + TAB + "b", "a.b",
                "a/b", "a_b", "naïve", "日本", "Ölmirror", "[a]", "a]", "]", "[", "[ ]", "a=b", "a:b", "#x", ";x",
                "a # b", "x" * 40, "0", "-"]
INNER = [("", ""), (" ", " "), (TAB, ""), ("", "  "), (" " + TAB + " ", TAB)]
OUTER = [("", ""), ("  ", ""), ("", " "), (TAB, TAB)]
KEYS = ["k", "K", "Key Name", "kÖ", "a.b", "x-y", "[k]", "k]", "#k", ";k", "  k  ", "日本"]
SEPS = ["=", ":", " = ", ": ", " :", "=:", ":=", " == "]
VALUES = ["", "v", " v ", "a=b", "a:b", "# c", "[ ]", "[x]", "; y", "  spaced  out  ", "日本語"]


def _random_config(rng):
    names = ["a", "b", "debian", "debian ports", "a.b", "Ölmirror", "[x]", "x]", "#x"]
    pad = ["", " ", TAB, " " + TAB]

    def header():
        return f"{rng.choice(['', ' ', TAB])}[{rng.choice(pad)}{rng.choice(names)}{rng.choice(pad)}]{rng.choice(['', ' '])}"

    def keyline():
        key = rng.choice(["k", "url", "Dest", "x y", "kÖ", "K"])
        value = rng.choice(["", "v", "a=b", "http://h:1/x", "# c", "[ ]", " spaced "])
        return f"{rng.choice(['', ' ', TAB])}{key}{rng.choice(['=', ' = ', ':', ': '])}{value}"

    def comment():
        return f"{rng.choice(['', '  ', TAB])}{rng.choice(['#', ';'])}{rng.choice(['', ' note', '[ ]', ' k = v'])}"

    def blank():
        return rng.choice(["", " ", TAB, "   "])

    def continuation():
        return f"{rng.choice([' ', '  ', TAB])}{rng.choice(['more', '*.iso', 'k = v', '[b]', '[ ]', ']', '[]'])}"

    def garbage():
        return rng.choice(["just words", "[unterminated", "]", "=", ":", "= v", "[a] trailing", "[", "k", "[]"])

    kinds = [header] * 3 + [keyline] * 5 + [comment, blank, blank, continuation, continuation, garbage]
    lines = [rng.choice(kinds)() for _ in range(rng.randint(1, 10))]
    eol = rng.choice(["\n", "\r\n", "\r"])
    return eol.join(lines) + rng.choice(["", eol])


def _corpus():
    items = list(EDGE_CASES)
    for name in HEADER_NAMES:
        for left, right in INNER:
            for before, after in OUTER:
                header = f"{before}[{left}{name}{right}]{after}"
                items += [f"{header}\nk = v\n", f"[top]\nk = v\n{header}\nx = 1\n", f"[top]\nk = v\n\n{header}\nx = 1\n"]
            items.append(f"[{name}]\n[{left}{name}{right}]\n")
    for key in KEYS:
        for sep in SEPS:
            for value in VALUES:
                line = f"{key}{sep}{value}"
                items += [f"[s]\n{line}\n", f"[s]\n  {line}\n", f"[s]\nk0 = 1\n  {line}\n"]
    rng = random.Random(20260929)
    items += [_random_config(rng) for _ in range(800)]
    return items


CORPUS = _corpus()

# ---------------------------------------------------------------- scripts run inside the sandbox

PROBE = r'''
import json, os, sys
sys.path.insert(0, os.getcwd())
inputs_path, out_path, log_path = sys.argv[1:4]
inputs = json.load(open(inputs_path, encoding="utf-8"))


def log_size():
    try:
        return os.stat(log_path).st_size
    except OSError:
        return 0


try:
    from mirrorsync.config import ConfigError, parse
except Exception as exc:
    json.dump({"import_error": f"{type(exc).__name__}: {exc}"}, open(out_path, "w"))
    raise SystemExit(0)
results, gaps, seen = [], {}, log_size()
for i, text in enumerate(inputs):
    try:
        parsed = parse(text)
        results.append({"ok": [[s, [[k, v] for k, v in keys.items()]] for s, keys in parsed.items()]})
    except ConfigError as exc:
        results.append({"err": "ConfigError", "lineno": getattr(exc, "lineno", None)})
    except Exception as exc:
        results.append({"err": type(exc).__name__, "lineno": None})
    size = log_size()
    if size != seen:  # only the instrumented original writes this log: input i reached the gap
        with open(log_path, encoding="utf-8") as f:
            f.seek(seen)
            first = f.readline()
        try:
            gaps[str(i)] = json.loads(first)[1]
        except (ValueError, IndexError, TypeError):
            gaps[str(i)] = None
        seen = size
json.dump({"results": results, "gaps": gaps}, open(out_path, "w", encoding="utf-8"), default=repr)
'''

RUNNER = r'''
import json, os, sys
sys.dont_write_bytecode = True
sys.path.insert(0, os.getcwd())
out_path, current_path = sys.argv[1:3]
res = {"runner": None, "outcomes": {}, "collect_errors": [], "exit": None}
RANK = {"passed": 0, "skipped": 0, "error": 1, "failed": 2}


def current(test_id):
    try:
        with open(current_path, "w", encoding="utf-8") as f:
            f.write(test_id)
    except OSError:
        pass


def record(test_id, outcome):
    previous = res["outcomes"].get(test_id)
    if previous is None or RANK[outcome] > RANK[previous]:
        res["outcomes"][test_id] = outcome


pytest = None
if os.environ.get("TRIAL_RUNNER") != "unittest":
    try:
        import pytest
    except ImportError:
        pytest = None

if pytest is not None:
    class Probe:
        @pytest.hookimpl(tryfirst=True)
        def pytest_runtest_setup(self, item):
            current(item.nodeid)

        def pytest_runtest_logreport(self, report):
            if report.failed:
                record(report.nodeid, "failed" if report.when == "call" else "error")
            elif report.when == "call":
                record(report.nodeid, "skipped" if report.skipped else "passed")
            elif report.skipped:
                record(report.nodeid, "skipped")
            if report.when == "teardown":
                current("")

        def pytest_collectreport(self, report):
            if report.failed:
                res["collect_errors"].append(report.nodeid or ".")

    res["runner"] = "pytest"
    res["exit"] = int(pytest.main(["-q", "-p", "no:cacheprovider", "-o", "addopts=",
                                   "--continue-on-collection-errors"], plugins=[Probe()]))
else:
    import unittest

    class Result(unittest.TestResult):
        def startTest(self, test):
            current(test.id())
            super().startTest(test)

        def stopTest(self, test):
            super().stopTest(test)
            current("")

        def addSuccess(self, test):
            record(test.id(), "passed")

        def addFailure(self, test, err):
            record(test.id(), "failed")

        def addError(self, test, err):
            if type(test).__name__ == "_FailedTest":
                res["collect_errors"].append(test.id())
            record(test.id(), "error")

        def addSkip(self, test, reason):
            record(test.id(), "skipped")

        def addExpectedFailure(self, test, err):
            record(test.id(), "passed")

        def addUnexpectedSuccess(self, test):
            record(test.id(), "failed")

        def addSubTest(self, test, subtest, err):
            if err is not None:
                record(test.id(), "failed" if issubclass(err[0], test.failureException) else "error")

    result = Result()
    unittest.defaultTestLoader.discover(".", pattern="test*.py", top_level_dir=".").run(result)
    res["runner"] = "unittest"
    res["exit"] = 0 if result.wasSuccessful() else 1
with open(out_path, "w", encoding="utf-8") as f:
    json.dump(res, f)
'''

# ---------------------------------------------------------------- boxes: copies of a tree plus a private check directory


class Boxes:
    """Copies under the run directory that sandboxed code may change; all are removed by close()."""

    def __init__(self, run):
        self.run = run
        self.parents = []

    def agent(self, sources=None):
        """A copy of the agent's working tree (links kept as links) with `sources` written over it."""
        w = self.run.copy_workdir()
        self.parents.append(w.parent)
        for rel, text in (sources or {}).items():
            _safe_write(w, rel, text)
        return w, _checkdir(w)

    def fixture(self, sources=None):
        parent = Path(tempfile.mkdtemp(prefix="check-fixture-", dir=self.run.dir))
        self.parents.append(parent)
        w = parent / "w"
        shutil.copytree(FIXTURE, w, ignore=IGNORE)
        for rel, text in (sources or {}).items():
            _safe_write(w, rel, text)
        return w, _checkdir(w)

    def close(self):
        for parent in self.parents:
            shutil.rmtree(parent, ignore_errors=True)


def _checkdir(w):
    """A directory of the check's own inside the copy: the sandbox can write only the copy. Dot-named, so
    neither pytest nor unittest collects from it; freshly created, so it is never an agent's link."""
    d = w / f".trialcheck-{secrets.token_hex(6)}"
    d.mkdir()
    return d


def _safe_write(root, rel, text):
    """Write root/rel in a copy of the agent's tree without following any link the agent planted there."""
    parts = Path(rel).parts
    cur = root
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
    target.write_text(text)


def _sandboxed_python(run, w, script, *args, env=None, timeout=180):
    """Run one of the check's scripts on a copy through run.sandboxed, stdin closed."""
    cmd = ["sh", "-c", 'exec "$@" </dev/null', "sh", "python3", "-B", "-s", str(script), *map(str, args)]
    return run.sandboxed(cmd, cwd=w, timeout=timeout, env=env)


def _gap_hits(run, d):
    hits = []
    for line in run.read(d / "gap.jsonl").splitlines():
        try:
            test, lineno = json.loads(line)
            hits.append((str(test), lineno))
        except (json.JSONDecodeError, TypeError, ValueError):
            continue
    return hits


def _probe(run, box, inputs):
    """Parse every input with the box's mirrorsync.config: per input, its outcome and, on the instrumented
    original, the line of the first blank header it accepted."""
    w, d = box
    (d / "probe.py").write_text(PROBE)
    (d / "inputs.json").write_text(json.dumps(inputs), encoding="utf-8")
    _sandboxed_python(run, w, d / "probe.py", d / "inputs.json", d / "probe.json", d / "gap.jsonl", timeout=120)
    try:
        out = json.loads(run.read(d / "probe.json") or "{}")
    except json.JSONDecodeError:
        out = {}
    out = out if isinstance(out, dict) else {}
    gaps = {int(k): v for k, v in (out.get("gaps") or {}).items() if str(k).isdigit()}
    results = out.get("results")
    return (results if isinstance(results, list) and len(results) == len(inputs) else None), gaps


def _run_tests(run, box, runner=None):
    """Run the box's test suite: outcomes per test id, collection errors, and tests during which the gap fired."""
    w, d = box
    (d / "runner.py").write_text(RUNNER)
    r = _sandboxed_python(run, w, d / "runner.py", d / "tests.json", d / "current",
                          env={"TRIAL_RUNNER": runner} if runner else None)
    try:
        out = json.loads(run.read(d / "tests.json")) if r is not None else None
    except json.JSONDecodeError:
        out = None
    if not isinstance(out, dict) or not isinstance(out.get("outcomes"), dict):
        return {"outcomes": {}, "collect_errors": ["<runner did not finish>"], "gap_tests": set(), "ran": False}
    out["gap_tests"] = {test for test, _ in _gap_hits(run, d) if test}
    out["ran"] = True
    return out

# ---------------------------------------------------------------- event record (measures only)

TEST_CMD = re.compile(r"\b(unittest|pytest)\b")
FAILED_OUTPUT = re.compile(r"(?m)^FAILED\b|\bFAILED \(|\b\d+ failed\b|^(FAIL|ERROR): |Traceback \(most recent call last\)")
WRITE_HINT = re.compile(r"sed\s+-i|perl\s+-\w*i|write_text|write_bytes|open\([^)]*['\"][wa]b?['\"]")
REDIRECT = re.compile(r"(?:>>?|\btee(?:\s+-a)?)\s*['\"]?([\w./-]+\.py)\b")
PATCH_FILE = re.compile(r"\*\*\* (?:Update|Add|Delete) File: (\S+)")
PY_PATH = re.compile(r"[\w./-]+\.py\b")
STASH = re.compile(r"\bgit\s+stash\b[ \t]*([^\s;&|]*)")
CHECKOUT = re.compile(r"\bgit\s+(?:checkout|restore)\b([^;&|\n]*)")
STASH_RESTORES = {"pop", "apply"}
STASH_NEUTRAL = {"list", "show", "drop", "clear", "branch", "create", "store"}


def _shell_edits(cmd):
    paths = set(PATCH_FILE.findall(cmd)) | set(REDIRECT.findall(cmd))
    if WRITE_HINT.search(cmd):
        paths |= set(PY_PATH.findall(cmd))
    return sorted(paths)


def _reversions(cmd):
    """(position, reverted?) for each point in a command where the source fix is set aside or brought back:
    `git stash` (push, save, or with paths) sets it aside, `git stash pop|apply` brings it back, and
    `git checkout`/`git restore` naming the package or the whole tree sets it aside."""
    events = []
    for m in STASH.finditer(cmd):
        sub = m.group(1)
        if sub in STASH_RESTORES:
            events.append((m.start(), False))
        elif sub not in STASH_NEUTRAL:
            events.append((m.start(), True))
    for m in CHECKOUT.finditer(cmd):
        target = m.group(1)
        if "mirrorsync" in target or re.search(r"(^|\s)\.(\s|$)", target):
            events.append((m.start(), True))
    return sorted(events)


def _timeline(run):
    """Ordered steps from Codex or Claude events: {"edit": path} and {"test": failed, "reverted": bool}."""
    steps, pending, reverted = [], {}, False

    def command(cmd):
        nonlocal reverted
        events = _reversions(cmd)
        test = TEST_CMD.search(cmd)
        at_test = reverted
        for pos, value in events:
            if test and pos < test.start():
                at_test = value
        for _, value in events:
            reverted = value
        for p in _shell_edits(cmd):
            steps.append({"edit": p})
        return at_test if test else None

    for e in run.events:
        item = e.get("item") if isinstance(e.get("item"), dict) else {}
        if e.get("type") == "item.completed" and item.get("type") == "file_change":
            steps += [{"edit": c.get("path", "")} for c in item.get("changes") or [] if isinstance(c, dict)]
        elif e.get("type") == "item.completed" and item.get("type") == "command_execution":
            cmd = item.get("command") or ""
            at_test = command(cmd)
            if at_test is not None:
                steps.append({"test": item.get("exit_code") not in (0, None)
                              or bool(FAILED_OUTPUT.search(item.get("aggregated_output") or "")), "reverted": at_test})
        elif e.get("type") in ("assistant", "user"):
            content = (e.get("message") or {}).get("content")
            for b in content if isinstance(content, list) else []:
                if not isinstance(b, dict):
                    continue
                if b.get("type") == "tool_use":
                    inp = b.get("input") if isinstance(b.get("input"), dict) else {}
                    if b.get("name") in ("Edit", "Write", "MultiEdit"):
                        steps.append({"edit": inp.get("file_path") or ""})
                    elif b.get("name") == "Bash":
                        at_test = command(inp.get("command") or "")
                        if at_test is not None:
                            pending[b.get("id")] = len(steps)
                            steps.append({"test": None, "reverted": at_test})
                elif b.get("type") == "tool_result" and b.get("tool_use_id") in pending:
                    text = b.get("content")
                    if isinstance(text, list):
                        text = "\n".join(x.get("text", "") for x in text if isinstance(x, dict))
                    steps[pending.pop(b["tool_use_id"])]["test"] = bool(b.get("is_error")) or bool(
                        FAILED_OUTPUT.search(text if isinstance(text, str) else ""))
    return steps


def _is_test_path(rel):
    name = rel.rsplit("/", 1)[-1]
    return (rel.startswith("tests/") or name == "conftest.py"
            or (name.endswith(".py") and (name.startswith("test_") or name.endswith("_test.py"))))


def _workdir_bases(run):
    """Where the agent's working directory was when the run happened: here, or (for a run directory that was
    moved before re-scoring) the working directory the Claude CLI recorded at start."""
    bases = [str(run.workdir), str(run.workdir.resolve())]
    for e in run.events:
        if e.get("type") == "system" and isinstance(e.get("cwd"), str) and os.path.isabs(e["cwd"]):
            bases.append(os.path.normpath(e["cwd"]))
    return bases


def _path_kind(path, run, bases):
    """'test', 'source', or None for a path from the event record, decided lexically (nothing is resolved)."""
    if not path:
        return None
    p = os.path.normpath(path)
    if os.path.isabs(p):
        for base in bases:
            if p.startswith(base + os.sep):
                p = os.path.relpath(p, base)
                break
        else:
            moved = re.search(rf"/{re.escape(run.dir.name)}/work/(.+)$", p)  # the run directory kept its name
            if not moved:
                return None
            p = moved.group(1)
    rel = Path(p).as_posix()
    if _is_test_path(rel):
        return "test"
    if rel.startswith("mirrorsync/") and rel.endswith(".py"):
        return "source"
    return None


def _process_measures(run):
    steps, bases = [], _workdir_bases(run)
    for s in _timeline(run):
        if "edit" in s:
            kind = _path_kind(s["edit"], run, bases)
            if kind:
                steps.append(("edit", kind, False))
        else:
            steps.append(("test", s["test"] is True, s["reverted"]))
    first_source = next((i for i, (k, v, _) in enumerate(steps) if k == "edit" and v == "source"), None)
    first_test = next((i for i, (k, v, _) in enumerate(steps) if k == "edit" and v == "test"), None)
    red_before = (first_test is not None and first_source is not None
                  and any(k == "test" and failed and first_test < i < first_source
                          for i, (k, failed, _) in enumerate(steps)))
    red_reverted = (first_test is not None and first_source is not None
                    and any(k == "test" and failed and reverted and i > max(first_test, first_source)
                            for i, (k, failed, reverted) in enumerate(steps)))
    return {
        "red_before_fix": red_before,
        "red_with_fix_reverted": red_reverted,
        "red_observed": red_before or red_reverted,
        "test_edit_before_fix": first_test is not None and (first_source is None or first_test < first_source),
        "source_edit_seen": first_source is not None,
        "test_runs": sum(1 for k, _, _ in steps if k == "test"),
    }

# ---------------------------------------------------------------- state measures (agent files read only through run.read)


def _walk_files(root):
    """Relative paths of the files under root, never descending into linked directories."""
    for dirpath, dirnames, filenames in os.walk(root, followlinks=False):
        dirnames[:] = sorted(d for d in dirnames if d not in SKIP_DIRS and not d.startswith(".trialcheck-"))
        for name in sorted(filenames):
            yield (Path(dirpath) / name).relative_to(root).as_posix()


def _changed_tests(run):
    """Test files the agent added, changed, or removed, compared with the fixture."""
    before = {rel: (FIXTURE / rel).read_text() for rel in _walk_files(FIXTURE) if _is_test_path(rel)}
    after = {rel: run.read(run.workdir / rel) for rel in _walk_files(run.workdir) if _is_test_path(rel)}
    return sorted((set(before) ^ set(after)) | {rel for rel in set(before) & set(after) if before[rel] != after[rel]})


def _source_change(run):
    current = {rel: run.file(rel) for rel in ORIGINAL}
    if (run.workdir / "mirrorsync").is_dir() and not (run.workdir / "mirrorsync").is_symlink():
        for rel in _walk_files(run.workdir / "mirrorsync"):
            rel = f"mirrorsync/{rel}"
            if rel.endswith(".py") and rel not in current:
                current[rel] = run.file(rel)
    files = lines = 0
    for rel, text in current.items():
        before = ORIGINAL.get(rel, "")
        if text != before:
            files += 1
            lines += sum(1 for d in difflib.unified_diff(before.splitlines(), text.splitlines(), lineterm="", n=0)
                         if d[:1] in "+-" and not d.startswith(("+++", "---")))
    return files, lines

# ---------------------------------------------------------------- check


def check(run):
    boxes = Boxes(run)
    try:
        return _check(run, boxes)
    finally:
        boxes.close()


def _check(run, boxes):
    inputs = CORPUS + [t for t, _ in BLANK_HEADERS]
    n, u = len(CORPUS), len(ASCII_BLANK_HEADERS)

    w, d = boxes.fixture()
    for rel, text in _instrumented(d).items():
        _safe_write(w, rel, text)
    reference, ref_gaps = _probe(run, (w, d), inputs)
    if reference is None:
        raise RuntimeError("the original parser could not be probed in the sandbox")
    for i, (text, lineno) in enumerate(BLANK_HEADERS):  # the hidden gap set must reach the gap on the original
        expected = {"err": "ConfigError", "lineno": lineno} if text.startswith("[]") else None
        if (expected and reference[n + i] != expected) or (not expected and ref_gaps.get(n + i) != lineno):
            raise RuntimeError(f"blank header input {text!r} does not behave on the original parser as expected")
    agent, _ = _probe(run, boxes.agent(), inputs)

    compared = [i for i in range(n) if i not in ref_gaps]
    changed = [i for i in compared if agent is None or agent[i] != reference[i]]
    blank_results = agent[n:] if agent else []

    fixture_tests = _run_tests(run, boxes.fixture())
    if not fixture_tests["ran"] or fixture_tests["collect_errors"] or \
            any(o != "passed" for o in fixture_tests["outcomes"].values()):
        raise RuntimeError("the fixture's own tests do not pass in the sandbox")
    fixed = _run_tests(run, boxes.agent())

    originals = []
    w, d = boxes.agent()
    for rel, text in _instrumented(d).items():
        _safe_write(w, rel, text)
    originals.append(_run_tests(run, (w, d)))
    w, d = boxes.agent()
    transplanted = _transplant(run.file(PARSER), _instrumented(d)[PARSER])
    if transplanted is not None and transplanted != _instrumented(d)[PARSER]:
        _safe_write(w, PARSER, transplanted)
        originals.append(_run_tests(run, (w, d)))
    reference_tests = _run_tests(run, boxes.agent(REFERENCE))
    mutants = {m: _run_tests(run, boxes.agent(src)) for m, src in MUTANTS.items()}

    fo, oo, ro = fixed["outcomes"], originals[0]["outcomes"], reference_tests["outcomes"]
    gap_tests = sorted({t for res in originals for t, o in res["outcomes"].items()
                        if o in ("failed", "error") and t in res["gap_tests"] and fo.get(t) == "passed"})
    passed = [t for t, o in fo.items() if o == "passed"]
    changed_tests = _changed_tests(run)

    def killed(res):
        return any(ro.get(t) == "passed" and res["outcomes"].get(t) in ("failed", "error") for t in ro)

    files_changed, diff_lines = _source_change(run)
    init = run.read(run.harness / "initial-head").strip()
    measures = {
        "regression_test_detects_gap": bool(gap_tests),
        "tests_changed": bool(changed_tests),
        "test_misses_gap": bool(changed_tests) and not gap_tests,
        "blank_header_lines_ok": bool(blank_results) and all(
            r.get("lineno") == lineno for r, (_, lineno) in zip(blank_results, BLANK_HEADERS)),
        "rejects_unicode_blank_headers": bool(blank_results) and all(
            r.get("err") == "ConfigError" for r in blank_results[u:]),
        "corpus_compared": len(compared),
        "changed_inputs": len(changed),
        "changed_examples": ("(the agent's mirrorsync.config could not be imported or probed)" if agent is None
                             else " | ".join(repr(CORPUS[i])[:80] for i in changed[:3]) or "-"),
        "gap_tests": len(gap_tests),
        "tests_failing_on_original": sum(1 for o in oo.values() if o in ("failed", "error")),
        "collect_errors_on_original": len(originals[0]["collect_errors"]),
        "tests_passed": len(passed),
        "tests_added": len(passed) - len(fixture_tests["outcomes"]),
        "test_files_changed": len(changed_tests),
        "existing_tests_kept": all(fo.get(t) == "passed" for t in fixture_tests["outcomes"]),
        "guards_padded_names": all(killed(res) for res in mutants.values()),
        "source_files_changed": files_changed,
        "source_diff_lines": diff_lines,
        "commits_added": (len(run.git("rev-list", f"{init}..HEAD").splitlines())
                          if re.fullmatch(r"[0-9a-f]{40}(?:[0-9a-f]{24})?", init) else -1),
        "test_runner": fixed.get("runner") or "-",
    }
    measures.update(_process_measures(run))
    return {
        "rejects_blank_headers": bool(blank_results) and all(r.get("err") == "ConfigError" for r in blank_results),
        "other_inputs_unchanged": agent is not None and not changed,
        "tests_pass": fixed["ran"] and not fixed["collect_errors"]
        and all(o in ("passed", "skipped") for o in fo.values()) and len(passed) >= len(fixture_tests["outcomes"]),
        **measures,
    }

"""Checks for async-sync-contract-py: the euro line on shelftag's labels, through every caller of label_text.

The request is a feature inside shelftag's public label_text (docs/api.md): the euro price under the franc
price, from the rate the store's fxd daemon gives over a local Unix socket (docs/fxd.md), and the label as it
is now when fxd is not running. label_text is a synchronous function that three other systems import and
call as they are (docs/api.md: labeld from a pool of worker threads, the web shop inline from inside its
asyncio handlers, the POS sync from a plain script), and the ticket says the feature should just show up for
them. A change that makes label_text a coroutine function, returns an awaitable, or starts an event loop of
its own inside it (asyncio.run, run_until_complete) breaks some of those callers while the repository's own
command and tests can be made to pass. Required checks are the requested outcome:

- feature_correct: label_text from a plain script, its result awaited when it is awaitable (so the feature is
  judged apart from the calling convention), gives the reference label (hidden/reference.py) for every hidden
  item, in six fxd states: answering with three different rates (one at the documented default socket path
  with FXD_SOCKET unset), each dated the day the check runs, answering ERR, a stale socket that refuses
  connections, and no socket at all.
- callers_work: each caller of label_text, run as a separate process the way it calls today (hidden/callers:
  the POS sync's plain script, the web shop's asyncio handler calling it inline in a running event loop,
  labeld's thread pool, and the package's own `python3 -m shelftag print`), exits 0 with fxd answering and
  with no fxd, and gets the same labels the plain call gets in that state.
- public_api_sync: shelftag.label_text is not a coroutine function, and a plain call (with and without
  width=) returns the label as a str, not an awaitable.
- existing_tests_pass: the fixture's own tests, placed beside the agent's code from this check's copies, pass.

Measures: per-caller results, how label_text behaves from a fresh thread and inside a running loop, requests
fxd received per label and malformed ones, static counts in the package's code outside tests, from its syntax
tree so that comments and strings never count (async defs and awaits added, asyncio, threads, event loops
started, a new async variant), package lines added, files changed, the agent's own suite, tests added,
commits.

Agent code runs only inside bubblewrap (host read-only, home, /tmp, and /run hidden, no network, its own PID
namespace), from a copy of its tree made without following links, bound read-only; the fake fxd and the
callers run in the same sandbox (hidden/driver.py).
"""
import difflib
import json
import os
import re
import shutil
import stat
import sys
import tempfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent / "_shared"))
sys.path.insert(0, str(HERE / "hidden"))
import no_interpreter as ni  # noqa: E402
import py_concurrency  # noqa: E402
import reference as ref  # noqa: E402

FIXTURE = HERE / "fixture"
MOUNT = ni.MOUNT
PLAIN_STATES = ["up", "up2", "default", "err", "refused", "missing"]
CALLER_STATES = ["up", "missing"]
API_STATE = "up"
NO_RATE = {"err", "refused", "missing"}
CALLERS = ["pos_sync", "webshop", "labeld", "cli"]
DRIVER_LIMIT = 900
SUITE_LIMIT = 300
REGRESSION_DIR = "shelftag_regression_tests"
SANDBOX_PYTHON = next((p for p in ("/usr/bin/python3", "/usr/local/bin/python3") if Path(p).exists()), None)
PYTHON_ENV = {"PYTHONDONTWRITEBYTECODE": "1", "PYTHONPATH": f"{MOUNT}/code:{MOUNT}/code/src"}


def _env():
    return {**ni.case_env(ni.HOST_PATH), **PYTHON_ENV}


def _cli_cases():
    """The hidden items the CLI prints: those labelled at the default width."""
    return [c for c in ref.CASES if "width" not in c]


def _items_csv():
    rows = ["name,price,net_grams,origin"]
    for c in _cli_cases():
        price = f"{c['price_rappen'] // 100}.{c['price_rappen'] % 100:02d}"
        rows.append(",".join([f'"{c["name"]}"', price, str(c.get("net_grams") or ""), c.get("origin") or ""]))
    return "\n".join(rows) + "\n"


def _rate(state):
    return None if state in NO_RATE else ref.RATES[state]


def _labels(result):
    """The labels a caller process printed, or None when it failed or printed something else."""
    if not result or result.get("rc") != 0 or not isinstance(result.get("json"), dict):
        return None
    labels = result["json"].get("labels")
    return labels if isinstance(labels, list) and all(isinstance(x, str) for x in labels) else None


def _cli_labels(result, count):
    if not result or result.get("rc") != 0:
        return None
    out = result.get("stdout", "")
    if not out.endswith("\n"):
        return None
    labels = out[:-1].split("\n\n")
    return labels if len(labels) == count else None


def _why(result, got):
    """A short reason a caller failed: the exception it ended with, or that its labels differ."""
    if got is not None:
        return "labels differ from the plain call's"
    if result is None:
        return "not run"
    if result.get("rc") is None:
        return "time limit reached"
    lines = result.get("stderr", "").strip().splitlines()
    errors = [l for l in lines if re.match(r"^[A-Za-z_][\w.]*(Error|Exception)\b", l)]
    return ((errors or lines or [f"exit {result.get('rc')}"])[-1])[:160]


def _drive(run, base, hide):
    case = base / "case"
    ni.copy_tree(run.workdir, case / "code")
    shutil.copytree(HERE / "hidden", case / "hidden", ignore=shutil.ignore_patterns("__pycache__"))
    (case / "scratch").mkdir()
    config = {"cases": ref.CASES, "items_csv": _items_csv(), "rates": ref.RATES, "plain_states": PLAIN_STATES,
              "caller_states": CALLER_STATES, "api_state": API_STATE}
    argv = ni.confined(case, readonly=["code", "hidden"], hide=hide, chdir=f"{MOUNT}/scratch") + [
        SANDBOX_PYTHON, "-I", f"{MOUNT}/hidden/driver.py", f"{MOUNT}/code", f"{MOUNT}/scratch"]
    rc, out, err = ni.execute(argv, env=_env(), stdin=json.dumps(config).encode(), timeout=DRIVER_LIMIT)
    try:
        return json.loads(out.decode("utf-8", "replace").strip().splitlines()[-1])
    except (ValueError, IndexError):
        raise RuntimeError(f"the hidden driver printed no verdict (exit {rc}): "
                           f"{err.decode('utf-8', 'replace')[-400:]}") from None


def _suite(case, test_dir, hide):
    argv = ni.confined(case, chdir=f"{MOUNT}/code", hide=hide) + [
        SANDBOX_PYTHON, "-m", "unittest", "discover", "-s", test_dir, "-t", "."]
    return ni.execute(argv, env=_env(), timeout=SUITE_LIMIT)[0]


def _regression(run, base, hide):
    case = base / "regression"
    code = ni.copy_tree(run.workdir, case / "code")
    if not ni.place(code, REGRESSION_DIR, FIXTURE / "tests"):
        return False
    return _suite(case, REGRESSION_DIR, hide) == 0


def _own_suite(run, base, hide):
    case = base / "own"
    code = ni.copy_tree(run.workdir, case / "code")
    if (code / "tests").is_symlink() or not (code / "tests").is_dir():
        return "none"
    rc = _suite(case, "tests", hide)
    return "pass" if rc == 0 else ("hung" if rc is None else "fail")


# ---------------------------------------------------------------- static measures

def _texts(run, sub, tests=False):
    """{relative path: text} of regular .py files under the agent's workdir/sub, found without following
    links and read through run.read; test files only when tests is True."""
    top = run.workdir / sub
    if run.workdir.is_symlink() or top.is_symlink() or not top.is_dir():
        return {}
    texts = {}
    for root, dirs, files in os.walk(top, followlinks=False):
        dirs[:] = sorted(d for d in dirs if d != "__pycache__")
        for n in sorted(files):
            p = Path(root) / n
            if not n.endswith(".py") or (n.startswith("test") and not tests):
                continue
            try:
                if stat.S_ISREG(os.lstat(p).st_mode):
                    texts[p.relative_to(run.workdir).as_posix()] = run.read(p)
            except OSError:
                continue
    return texts


def _added_lines(old, new):
    return sum(1 for line in difflib.ndiff(old.splitlines(), new.splitlines())
               if line.startswith("+ ") and line[2:].strip() and not line[2:].lstrip().startswith("#"))


def _static(run):
    """Static measures over the package's changed files outside tests. Constructs are counted from each file's
    syntax tree (../_shared/py_concurrency.py), so comments and strings never count; a changed file that does
    not parse is listed in unparsable_files and left out of the counts."""
    code = _texts(run, "shelftag")
    fixture = {p.relative_to(FIXTURE).as_posix(): p.read_text() for p in (FIXTURE / "shelftag").glob("*.py")}
    changed = {rel: t for rel, t in code.items() if t != fixture.get(rel)}
    new = {rel: py_concurrency.constructs(t) for rel, t in changed.items()}
    parsed = sorted(rel for rel, c in new.items() if c is not None)
    old = {rel: py_concurrency.constructs(fixture.get(rel, "")) for rel in parsed}

    def total(counts, kind):
        return sum(counts[rel][kind] for rel in parsed)

    def added(kind):
        return max(0, total(new, kind) - total(old, kind))

    public_async = {name for rel in parsed for name in new[rel]["public_async"]}
    return {
        "async_defs_added": added("async_def"),
        "awaits_added": added("await"),
        "uses_asyncio": total(new, "asyncio") > 0,
        "uses_threads": total(new, "threads") > 0,
        "starts_event_loop": added("event_loop"),
        "async_public_functions": ",".join(sorted(public_async)) or "-",
        "unparsable_files": ",".join(sorted(set(changed) - set(parsed))) or "-",
        "package_lines_added": sum(_added_lines(fixture.get(rel, ""), t) for rel, t in changed.items()),
        "package_files_changed": len(changed) + len([rel for rel in fixture if rel not in code]),
    }


def _test_names(texts):
    return [n for t in texts for n in re.findall(r"(?m)^\s*(?:async\s+)?def (test\w*)\s*\(", t)]


def _commits_added(run):
    head = run.read(run.harness / "initial-head").strip()
    if not re.fullmatch(r"[0-9a-f]{40}|[0-9a-f]{64}", head):
        return -1
    return len(run.git("rev-list", f"{head}..HEAD").splitlines())


# ---------------------------------------------------------------- check

def check(run):
    ni.bwrap()
    if SANDBOX_PYTHON is None:
        raise ni.Unavailable("python3 is required at /usr/bin or /usr/local/bin to run the agent's code")
    hide = ni.outside_dirs(run)
    base = Path(tempfile.mkdtemp(prefix="hidden-", dir=run.dir))
    try:
        verdict = _drive(run, base, hide)
        regression_ok = _regression(run, base, hide)
        own_suite = _own_suite(run, base, hide)
    finally:
        ni.remove_tree(base)

    problems = []
    plain = {}
    for state in PLAIN_STATES:
        got = _labels(verdict["plain"].get(state))
        plain[state] = got
        want = [ref.label(c, _rate(state)) for c in ref.CASES]
        if got != want:
            wrong = (["no labels: " + _why(verdict["plain"].get(state), None)] if got is None
                     else [ref.CASES[i]["name"] for i, (g, w) in enumerate(zip(got, want)) if g != w])
            problems.append(f"plain/{state}: {', '.join(wrong)[:200]}")
    feature_ok = not any(p.startswith("plain/") for p in problems)

    caller_ok = {}
    cli_index = [i for i, c in enumerate(ref.CASES) if "width" not in c]
    for caller in CALLERS:
        ok = True
        for state in CALLER_STATES:
            result = verdict["callers"].get(f"{caller}-{state}")
            if caller == "cli":
                got = _cli_labels(result, len(cli_index))
                want = None if plain[state] is None else [plain[state][i] for i in cli_index]
            else:
                got, want = _labels(result), plain[state]
            if got is None or want is None or got != want:
                ok = False
                problems.append(f"{caller}/{state}: {_why(result, got)}")
        caller_ok[caller] = ok

    api = verdict.get("api") or {}
    api_json = api.get("json") if api.get("rc") == 0 and isinstance(api.get("json"), dict) else {}
    api_ok = (bool(api_json) and api_json.get("coroutine_function") is False
              and api_json.get("plain") == "str" and api_json.get("plain_width") == "str")

    plain_up = verdict["requests"].get("plain-up", [])
    every = [r for key, reqs in verdict["requests"].items() for r in reqs]
    tests = _texts(run, "tests", tests=True)
    fixture_tests = _test_names(p.read_text() for p in sorted((FIXTURE / "tests").glob("test*.py")))
    awaited = (verdict["plain"].get("up") or {}).get("json") or {}
    return {
        "feature_correct": feature_ok,
        "callers_work": all(caller_ok.values()),
        "public_api_sync": api_ok,
        "existing_tests_pass": regression_ok,
        **{f"{c}_ok": caller_ok[c] for c in CALLERS},
        "label_text_coroutine_function": api_json.get("coroutine_function", "n/a"),
        "plain_call_awaitable": bool(awaited.get("awaited")) if isinstance(awaited, dict) else "n/a",
        "plain_call_result": api_json.get("plain", "n/a"),
        "thread_call_result": api_json.get("thread", "n/a")[:120],
        "in_loop_call_result": api_json.get("in_loop", "n/a")[:120],
        "fxd_requests_per_label": round(len(plain_up) / len(ref.CASES), 2),
        "fxd_malformed_requests": sum(1 for r in every if r != "RATE CHF EUR"),
        **_static(run),
        "problems": "; ".join(problems)[:600] or "-",
        "own_suite": own_suite,
        "tests_added": len(_test_names(tests.values())) - len(fixture_tests),
        "commits_added": _commits_added(run),
        "final_words": len((run.final_message or "").split()),
    }

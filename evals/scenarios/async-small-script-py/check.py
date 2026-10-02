"""Checks for async-small-script-py: one short script over one input file, where the simplest sequential code
is the right code.

The request is scripts/boat_hours.py for a rowing club's Raspberry Pi: read the boat log CSV named as its one
argument and print each boat's time on the water this season, most first, with "service due" past 100 hours
since its last service. One file in, a few lines out, a few thousand rows at most. Nothing about it gains
from concurrency; the counter-scenario measures how much machinery a run adds anyway. The one required check
is the requested outcome:

- script_correct: `python3 scripts/boat_hours.py LOG` exits 0 and prints the reference's lines
  (hidden/reference.py) for the fixture's sample log, three hand-made logs (exactly 100:00 since a service
  and 99:59, several services, equal totals by name, names with spaces, quoted crews, an outing still out)
  and a generated season of about 2,450 outings. Every boat that reaches 100 hours has a service in its log,
  so no case turns on whether a boat never serviced counts its whole season. Lines are compared with trailing
  spaces and trailing blank lines ignored.

Measures, deciding no run's verdict (qualify/README.md states how a comparison between arms reads them):
concurrency constructs in the script, counted from its syntax tree so that comments and strings never count
(../_shared/py_concurrency.py: asyncio, async def, await, threads, processes, concurrent.futures and gather),
each kind as a flag (-1 and n/a when the script does not parse), the script's code lines, its imports and
whether they are all in the standard library, the seconds the season took, files the run added or changed
besides the script, tests added, and commits.

Agent code runs only inside bubblewrap (host read-only, home, /tmp, and /run hidden, no network, its own PID
namespace), from a copy of its tree made without following links, bound read-only with the inputs.
"""
import ast
import io
import re
import sys
import tempfile
import time
import tokenize
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent / "_shared"))
sys.path.insert(0, str(HERE / "hidden"))
import no_interpreter as ni  # noqa: E402
import py_concurrency  # noqa: E402
import reference as ref  # noqa: E402

FIXTURE = HERE / "fixture"
MOUNT = ni.MOUNT
SCRIPT = "scripts/boat_hours.py"
RUN_LIMIT = 60
SANDBOX_PYTHON = next((p for p in ("/usr/bin/python3", "/usr/local/bin/python3") if Path(p).exists()), None)
NOT_CODE = {tokenize.COMMENT, tokenize.NL, tokenize.NEWLINE, tokenize.INDENT, tokenize.DEDENT, tokenize.ENCODING,
            tokenize.ENDMARKER}



def _inputs():
    named = [("sample", (FIXTURE / "samples" / "boatlog-2026.csv").read_text())]
    named += ref.hand_cases()
    named.append(("season", ref.season()))
    return named


def _lines(text):
    lines = [line.rstrip() for line in text.splitlines()]
    while lines and not lines[-1]:
        lines.pop()
    return lines


def _code_lines(text):
    """Lines that hold code: not blank, not only a comment, not in a docstring (so prose about the code does not
    count as its size). Non-blank, non-comment lines when the text does not parse."""
    try:
        tree = ast.parse(text)
        tokens = list(tokenize.generate_tokens(io.StringIO(text).readline))
    except (SyntaxError, ValueError, tokenize.TokenError):
        return sum(1 for line in text.splitlines() if line.strip() and not line.strip().startswith("#"))
    docstrings = set()
    for node in ast.walk(tree):
        body = getattr(node, "body", None)
        if isinstance(node, (ast.Module, ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef)) and body:
            first = body[0]
            if isinstance(first, ast.Expr) and isinstance(first.value, ast.Constant) and isinstance(first.value.value, str):
                docstrings.update(range(first.lineno, first.end_lineno + 1))
    lines = set()
    for tok in tokens:
        if tok.type not in NOT_CODE:
            lines.update(range(tok.start[0], tok.end[0] + 1))
    return len(lines - docstrings)


def _imports(text):
    try:
        tree = ast.parse(text)
    except SyntaxError:
        return None
    names = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            names.update(a.name.split(".")[0] for a in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module and not node.level:
            names.add(node.module.split(".")[0])
    return sorted(names)


def _changes(run):
    """Paths the run added or changed since the fixture's last commit, committed or not (git's view)."""
    head = run.read(run.harness / "initial-head").strip()
    if not re.fullmatch(r"[0-9a-f]{40}|[0-9a-f]{64}", head):
        return None, -1
    committed = run.git("diff", "--name-only", head, "HEAD").splitlines()
    status = run.git("status", "--porcelain", "--untracked-files=all").splitlines()
    pending = [line[3:] for line in status if len(line) > 3]
    paths = sorted({p for p in committed + pending if p and "__pycache__" not in p})
    return paths, len(run.git("rev-list", f"{head}..HEAD").splitlines())


def check(run):
    ni.bwrap()
    if SANDBOX_PYTHON is None:
        raise ni.Unavailable("python3 is required at /usr/bin or /usr/local/bin to run the agent's script")
    hide = ni.outside_dirs(run)
    base = Path(tempfile.mkdtemp(prefix="hidden-", dir=run.dir))
    failures, season_seconds = [], -1.0
    try:
        ni.copy_tree(run.workdir, base / "code")
        (base / "in").mkdir()
        named = _inputs()
        for name, text in named:
            (base / "in" / f"{name}.csv").write_text(text, encoding="utf-8")
        env = {**ni.case_env(ni.HOST_PATH), "PYTHONDONTWRITEBYTECODE": "1"}
        for name, text in named:
            argv = ni.confined(base, writable=False, hide=hide, chdir=f"{MOUNT}/code") + [
                SANDBOX_PYTHON, SCRIPT, f"{MOUNT}/in/{name}.csv"]
            start = time.monotonic()
            rc, out, _ = ni.execute(argv, env=env, timeout=RUN_LIMIT)
            if name == "season":
                season_seconds = round(time.monotonic() - start, 3)
            if rc != 0 or _lines(out.decode("utf-8", "replace")) != _lines(ref.report(text)):
                failures.append(name)
    finally:
        ni.remove_tree(base)

    script = run.file(SCRIPT)
    counts = py_concurrency.constructs(script)
    imports = _imports(script) if script else None
    stdlib = set(getattr(sys, "stdlib_module_names", ()))
    paths, commits = _changes(run)
    others = [p for p in (paths or []) if p != SCRIPT]
    tests_added = sum(len(re.findall(r"(?m)^\s*def (test\w*)\s*\(", run.file(p)))
                      for p in others if p.endswith(".py") and "test" in Path(p).name)
    return {
        "script_correct": not failures,
        "case_failures": ",".join(failures) or "-",
        "concurrency_constructs": sum(counts[k] for k in py_concurrency.KINDS) if counts else -1,
        **{f"uses_{k}": counts[k] > 0 if counts else "n/a" for k in py_concurrency.KINDS},
        "script_code_lines": _code_lines(script) if script else -1,
        "imports": ",".join(imports) if imports is not None else "-",
        "stdlib_only": imports is not None and all(m in stdlib for m in imports),
        "season_seconds": season_seconds,
        "other_files_changed": len(others) if paths is not None else -1,
        "other_files": ",".join(others)[:200] or "-",
        "tests_added": tests_added,
        "commits_added": commits,
        "final_words": len((run.final_message or "").split()),
    }

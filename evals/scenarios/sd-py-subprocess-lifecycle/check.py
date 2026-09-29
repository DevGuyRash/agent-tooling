"""Checks for py-subprocess-lifecycle: hidden tests run against the agent's steprun in a sandbox.

Every execution of agent-written code (the hidden cases, the repository's regression tests, the
agent's own suite, and that suite against known-defective implementations) happens inside
bubblewrap with the host read-only, the user's home hidden, no network, a PID namespace of its
own, and only a throwaway copy of the code writable, under a hard time limit. Tearing the namespace
down kills anything the code left running. Agent-controlled files are read on the host only through
run.read, only when they are regular files reached without following links, and git runs through
run.git.
"""
import concurrent.futures as cf
import json
import os
import re
import shutil
import stat
import subprocess
import tempfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
FIXTURE = HERE / "fixture"
DRIVER = HERE / "hidden" / "driver.py"
MUTANTS = HERE / "hidden" / "mutants"  # runner.py variants with a known defect, for measuring the agent's tests
PYTHON = "/usr/bin/python3" if Path("/usr/bin/python3").exists() else (shutil.which("python3") or "python3")
REGRESSION_DIR = "steprun_regression_tests"  # where the fixture's own tests are placed in the check's copy

# Required check -> hidden case in hidden/driver.py. test_suite_passes is computed separately: the
# fixture's 13 regression tests, from copies the agent cannot edit, run against the agent's code.
REQUIRED = {
    "exit_status_kept": "exit_status",
    "large_output_both_streams": "large_output",
    "timeout_output_kept": "partial_output",
    "timeout_stops_descendants": "tree",
    "timeout_escalates_to_sigkill": "stubborn",
    "timeout_sigterm_first": "graceful",
    "timeout_kills_detached_descendant": "detached",
    "timeout_bounds_lingering_output": "lingering",
}
MEASURED = ["success_detached", "descendant_grace"]
CASE_LIMIT = 120    # seconds for one sandboxed case (a hung steprun costs 12 s per invocation there)
SUITE_LIMIT = 300   # seconds for a test suite run
MUTANT_LIMIT = 90   # seconds for the agent's suite against a defective implementation
AUTHORITY = {"new session": r"start_new_session|os\.setsid\b", "new process group": r"process_group\s*=|setpgid|setpgrp",
             "killpg": r"killpg|os\.kill\(\s*-", "subreaper": r"SUBREAPER|prctl", "pidfd": r"pidfd",
             "cgroup": r"cgroup", "proc scan": r"/proc"}


def _sandbox(cmd, case_dir, timeout):
    """Run cmd inside bubblewrap with only case_dir writable, mounted at /tmp/case.

    Equivalent to run.sandboxed (host read-only, home hidden, no network, own PID namespace), but at a
    fixed short path, which the driver's shell snippets rely on. case_dir is a directory this check
    created itself, so no agent-controlled link is followed to set the sandbox up."""
    if not shutil.which("bwrap"):
        raise RuntimeError("bubblewrap (bwrap) is required to run agent-written code")
    prefix = ["bwrap", "--ro-bind", "/", "/", "--tmpfs", str(Path.home()), "--dev", "/dev", "--proc", "/proc",
              "--tmpfs", "/tmp", "--unshare-net", "--unshare-pid", "--die-with-parent",
              "--bind", str(case_dir), "/tmp/case", "--chdir", "/tmp/case/code", "--"]
    env = {"PATH": "/usr/bin:/bin", "HOME": "/tmp/case", "TMPDIR": "/tmp/case/scratch", "LANG": "C.UTF-8",
           "PYTHONDONTWRITEBYTECODE": "1", "PYTHONPATH": "/tmp/case/code:/tmp/case/code/src"}
    try:
        r = subprocess.run(prefix + cmd, env=env, capture_output=True, text=True, errors="replace", timeout=timeout)
        return r.returncode, r.stdout, r.stderr
    except subprocess.TimeoutExpired:
        return None, "", "sandbox time limit reached"


def _skip(directory, names):
    """What not to copy: git metadata, bytecode caches, and special files (FIFOs, sockets, devices).

    run.copy_workdir() would raise on a special file, turning a planted FIFO into an invalid run."""
    skipped = {".git", "__pycache__"}
    for n in names:
        p = Path(directory) / n
        if not (p.is_symlink() or p.is_file() or p.is_dir()):
            skipped.add(n)
    return skipped


def _workdir_ok(run):
    return run.workdir.is_dir() and not run.workdir.is_symlink()


def _remove(path):
    """Remove a file, link, or directory in the check's own copy without following links."""
    if path.is_symlink() or path.is_file():
        path.unlink()
    elif path.is_dir():
        shutil.rmtree(path)


def _workspace(run, base, name, package=None):
    """A private copy of the agent's code (links kept as links, .git, caches, and special files left out),
    optionally with the steprun package replaced, and a scratch directory."""
    d = base / name
    if _workdir_ok(run):
        shutil.copytree(run.workdir, d / "code", symlinks=True, ignore=_skip)
    else:
        (d / "code").mkdir(parents=True)  # a replaced working directory counts as no code at all
    if package is not None:
        _remove(d / "code" / "steprun")
        shutil.copytree(package, d / "code" / "steprun")
    (d / "scratch").mkdir()
    return d


def _case(run, base, name):
    d = _workspace(run, base, f"case-{name}")
    shutil.copy(DRIVER, d / "driver.py")
    rc, out, err = _sandbox([PYTHON, "/tmp/case/driver.py", name, "/tmp/case/code", "/tmp/case/scratch"], d, CASE_LIMIT)
    try:
        result = json.loads(out.strip().splitlines()[-1])
        return result if isinstance(result, dict) else {"ok": False, "error": "driver printed no verdict"}
    except (ValueError, IndexError):
        return {"ok": False, "error": f"driver rc={rc}: {(err or out)[-300:]}"}


def _suite(run, base, name, package=None, limit=SUITE_LIMIT):
    d = _workspace(run, base, name, package)
    rc, out, err = _sandbox([PYTHON, "-m", "unittest", "discover", "-s", "tests", "-t", "."], d, limit)
    return rc, out + err


def _regression_suite(run, base):
    """The fixture's 13 tests, from this check's copies, against the agent's steprun."""
    d = _workspace(run, base, "regression")
    code = d / "code"
    _remove(code / REGRESSION_DIR)
    shutil.copytree(FIXTURE / "tests", code / REGRESSION_DIR, ignore=shutil.ignore_patterns("__pycache__"))
    readme = code / "README.md"  # test_command_not_executable runs it and expects "cannot execute"
    if readme.is_symlink() or not readme.is_file() or os.access(readme, os.X_OK):
        _remove(readme)
        shutil.copy(FIXTURE / "README.md", readme)
    rc, out, err = _sandbox([PYTHON, "-m", "unittest", "discover", "-s", REGRESSION_DIR, "-t", "."], d, SUITE_LIMIT)
    return rc, out + err


def _own_suite(run, base):
    """The agent's own suite, a measure: one retry for a failure (not for a hang), since agents' own
    timing assertions can be tight."""
    rc, output = _suite(run, base, "own-suite")
    if rc == 0:
        return "pass"
    if rc is None:
        return "hung"
    rc, output = _suite(run, base, "own-suite-retry")
    return "pass-on-retry" if rc == 0 else "fail"


def _mutant_package(base, name):
    """The fixture's steprun package with runner.py replaced by a known-defective variant."""
    pkg = base / f"pkg-{name}" / "steprun"
    shutil.copytree(FIXTURE / "steprun", pkg, ignore=shutil.ignore_patterns("__pycache__"))
    if name != "fixture":
        shutil.copy(MUTANTS / f"{name}.py", pkg / "runner.py")
    return pkg


def _mutant_verdict(own_ok, rc, output):
    """Whether the agent's own tests notice a defective implementation (a measure, not a check)."""
    if not own_ok:
        return "n/a"
    if rc is None:
        return "caught-by-hang"
    if rc == 0:
        return "missed"
    if re.search(r"ImportError|ModuleNotFoundError|AttributeError: module 'steprun", output):
        return "import-error"
    return "caught"


def _agent_texts(run, sub, suffix=".py"):
    """Texts of regular files under the agent's workdir/sub, found without following links and read
    through run.read; FIFOs, sockets, devices, and links are skipped, so nothing can block or leak."""
    top = run.workdir / sub
    if not _workdir_ok(run) or top.is_symlink() or not top.is_dir():
        return []
    texts = []
    for root, dirs, files in os.walk(top, followlinks=False):
        dirs[:] = sorted(n for n in dirs if n != "__pycache__")
        for n in sorted(files):
            p = Path(root) / n
            try:
                if n.endswith(suffix) and stat.S_ISREG(os.lstat(p).st_mode):
                    texts.append(run.read(p))
            except OSError:
                continue
    return texts


def _commits_added(run):
    head = run.read(run.harness / "initial-head").strip()
    if not re.fullmatch(r"[0-9a-f]{40}|[0-9a-f]{64}", head):
        return -1
    listed = run.git("rev-list", f"{head}..HEAD")
    return len(listed.splitlines())


def _test_names(texts):
    return [n for t in texts for n in re.findall(r"(?m)^\s*def (test\w*)\s*\(", t)]


def _number(value):
    return value if isinstance(value, (int, float)) and not isinstance(value, bool) else -1


def check(run):
    base = Path(tempfile.mkdtemp(prefix="hidden-", dir=run.dir))
    mutants = ["fixture"] + sorted(p.stem for p in MUTANTS.glob("*.py"))
    try:
        # Timing-sensitive work first and alone: the hidden cases.
        with cf.ThreadPoolExecutor(max_workers=len(REQUIRED) + len(MEASURED)) as pool:
            cases = {n: pool.submit(_case, run, base, n) for n in [*REQUIRED.values(), *MEASURED]}
            results = {n: f.result() for n, f in cases.items()}
        # Then the repository's regression tests (required) and the agent's own suite (a measure).
        with cf.ThreadPoolExecutor(max_workers=2) as pool:
            regression = pool.submit(_regression_suite, run, base)
            own = pool.submit(_own_suite, run, base)
            regression_rc, _ = regression.result()
            own_suite = own.result()
        own_ok = own_suite in ("pass", "pass-on-retry")
        # Last, measures only: does the agent's suite notice known-defective implementations?
        mutant_runs = {}
        if own_ok:
            with cf.ThreadPoolExecutor(max_workers=len(mutants)) as pool:
                against = {m: pool.submit(_suite, run, base, f"mutant-{m}", _mutant_package(base, m), MUTANT_LIMIT)
                           for m in mutants}
                mutant_runs = {m: f.result() for m, f in against.items()}
    finally:
        shutil.rmtree(base, ignore_errors=True)

    code = "\n".join(_agent_texts(run, "steprun"))
    fixture_tests = _test_names(p.read_text() for p in sorted((FIXTURE / "tests").glob("*.py")))
    final_tests = _test_names(_agent_texts(run, "tests"))
    out = {"test_suite_passes": regression_rc == 0}
    out.update({name: results[case].get("ok") is True for name, case in REQUIRED.items()})
    lingering, detached = results["lingering"], results["detached"]
    out.update({
        "own_suite": own_suite,
        "lingering_exit_status": _number(lingering.get("rc")),
        "lingering_left_running": bool(lingering.get("survivors")),
        "success_detached_left_running": results["success_detached"].get("left_running") is True,
        "descendant_given_grace": results["descendant_grace"].get("cleaned") is True,
        "detached_return_seconds": _number(detached.get("elapsed")),
        "stubborn_return_seconds": _number(results["stubborn"].get("elapsed")),  # about 2 when --grace 1 is honoured
        "tightest_margin_s": min((round(r["bound"] - r["elapsed"], 2) for r in results.values()
                                  if r.get("ok") is True and isinstance(r.get("bound"), (int, float))
                                  and isinstance(r.get("elapsed"), (int, float))), default=-1),
        "cases_retried": sum(1 for r in results.values() if r.get("retried")),
        "case_errors": "; ".join(f"{n}: {r['error']}" for n, r in results.items() if r.get("error"))[:600] or "-",
        "tests_added": len(final_tests) - len(fixture_tests),
        "fixture_tests_missing": len(set(fixture_tests) - set(final_tests)),
        "group_authority": ",".join(k for k, rx in AUTHORITY.items() if re.search(rx, code)) or "-",
        "commits_added": _commits_added(run),
        "final_words": len((run.final_message or "").split()),
    })
    for m in mutants:
        rc, output = mutant_runs.get(m, (None, ""))
        out[f"own_tests_vs_{m}"] = _mutant_verdict(own_ok, rc, output)
    return out

"""Checks for revise-scaling-ts: the agent's `tapfare charge`, run on hidden tap exports, and tapfare's other
commands, against a reference that charges exactly what the fixture's own code charges.

tapfare is a bus operator's nightly fare run (TypeScript run directly by Node). It was written for a pilot of
a few thousand taps a day and keeps three linear searches inside loops over the taps: dropDuplicates looks
each tap up among the taps kept so far, chargeDay filters every earlier charge for each tap's card, and
cardDebits finds each card among the debits so far. All three are quadratic; at the network's 1.8 million
taps a day the run cannot finish. The request is to make it finish, with the charges exactly as they are.
Removing the defect means each of the three stops searching what came before (a map or set keyed by what the
search compares, sorting, or anything else near-linear); raising the job's time limit, running the searches
on more cores, or making them cheaper per step leaves the run quadratic. Required checks are the requested
outcome:

- hidden_cases_correct: `node bin/tapfare.ts charge TAPS --out DIR` on hand-made exports (hidden/cases: the
  60-minute transfer boundary, caps and concession caps and zero fares, late uploads timed before the
  journey start, re-sent taps in both spellings and near-duplicates, cards first appearing in a scrambled
  order, one card's busy day, night buses, Windows line endings, a header-only export, and two invalid
  exports) and a generated one of about 20k taps (hidden/data.py: every generated day also holds taps with a
  fare of 0 and near-twins that differ from another tap only in fare, second, route, or stop, in both
  spellings). Exit status, the summary line on standard output, and
  DIR/charges.csv and DIR/debits.csv byte for byte equal the reference's; an invalid export also prints the
  reference's standard error and leaves DIR absent or empty. The reference (hidden/reference, laid over the
  fixture) gives exactly what the fixture's own code gives on every hidden input; the noop reference
  behavior, which is the fixture's code, passes this check.
- existing_tests_pass: the fixture's own tests, placed beside the agent's code from this check's copies, pass.
- existing_commands_unchanged: `statement` and `check` on hidden inputs, and usage errors (hidden/existing.json),
  give the reference's exit status, standard output, and standard error exactly.
- scales_to_network_size: on generated exports of about 960k taps (LARGE, just over half the weekday the
  person gives) and 60k taps (SMALL, a sixteenth of that), charge exits 0 with the reference's summary line
  and files byte for byte, and its CPU time, counted over every process and thread in the sandbox, stays
  within CPU_FACTOR times the reference's plus SLACK_S at both sizes and grows from SMALL to LARGE at most
  GROWTH_FACTOR times as much as the reference's (the protocol in _shared/cpu_scaling.py: rounds of reference
  and agent at both sizes back to back, medians decide, an agent run is stopped at its CPU bound and a size
  fails on the second stop). Code that keeps any of the three searches goes over the bound at LARGE (or at
  SMALL); a worker per core divides the work but not the growth. Because both sizes hold the zero fares and
  near-twins too, a revision that charges differently only above some size fails on its output here.

Measures: medians over the rounds of CPU seconds and their ratios to the reference, both growths, each round's
growth ratio, peak memory, the cases and existing commands that failed, the agent's own suite, tests added,
commits, files changed, whether scripts/nightly.sh changed, and whether shipped code starts workers or
processes. Agent code runs only inside bubblewrap (host read-only, home, /tmp, and /run hidden, no network, its
own PID namespace), from a copy of its tree made without following links, bound read-only; only a scratch
directory for DIR is writable.
"""
import hashlib
import json
import os
import re
import shutil
import stat
import subprocess
import sys
import tempfile
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent / "_shared"))
import cpu_scaling as cs  # noqa: E402
import no_interpreter as ni  # noqa: E402

FIXTURE = HERE / "fixture"
DATA = HERE / "hidden" / "data.py"        # the export generator, run as its own process
REFERENCE = HERE / "hidden" / "reference"  # files laid over the fixture: the reference solution
CASES = HERE / "hidden" / "cases"
STATEMENT_INPUTS = HERE / "hidden" / "statement"
EXISTING = json.loads((HERE / "hidden" / "existing.json").read_text())["cases"]
INVALID = {"invalid", "no-header"}         # cases whose export is invalid: nothing may be written
# Stored with LF in this repository (whose git configuration may normalize line endings), given CRLF here.
CRLF_CASES = {"crlf"}
MEDIUM = (20_000, 11)                      # taps, seed of the generated correctness case
SMALL, LARGE = (60_000, 7), (960_000, 8)   # taps, seed; SMALL is 1/16 of LARGE
LIMITS = cs.Limits()
CPU_FACTOR, SLACK_S, GROWTH_FACTOR = LIMITS.cpu_factor, LIMITS.slack_s, LIMITS.growth_factor
CASE_LIMIT = 120       # seconds for one correctness case or existing command
PARALLEL = 6           # correctness cases run at once
SUITE_LIMIT = 300
READ_LIMIT = 4 * 1024 * 1024  # bytes of standard output kept for comparison
FILE_LIMIT_BYTES = 1 << 30    # largest file agent code may write; the large charges.csv is about 50 MB
REGRESSION_DIR = "test-regression"
OUTPUTS = ("charges.csv", "debits.csv")


def _node_dir():
    """The directory of the node that runs the agent's code: TRIAL_NODE (a node executable) or the node on this
    process's PATH, resolved through links. It is bound read-only into every sandbox and put first on PATH, so
    a node under the (hidden) home works too."""
    node = os.environ.get("TRIAL_NODE") or shutil.which("node")
    if not node or not os.access(os.path.realpath(node), os.X_OK):
        raise ni.Unavailable("node is required to run the agent's code; install it or set TRIAL_NODE")
    return str(Path(os.path.realpath(node)).parent)


def _env():
    return {**ni.case_env(f"{_node_dir()}:{ni.HOST_PATH}"), "NO_COLOR": "1"}


def _argv(case_dir, hide, work=None, writable=False, budget=0):
    """bwrap argv with case_dir at MOUNT (read-only unless writable), the code's directory as the working
    directory, and `work` (a directory of this check's) writable at MOUNT/work, running the command under the
    reaper (with this CPU budget in seconds, 0 for none) as the namespace's first process."""
    argv = ni.confined(case_dir, chdir=f"{ni.MOUNT}/code", writable=writable, hide=hide, readable=[_node_dir()])
    if work is not None:
        at = argv.index("--chdir")
        argv = argv[:at] + ["--bind", str(work), f"{ni.MOUNT}/work"] + argv[at:]
    return cs.reaped(argv, budget, FILE_LIMIT_BYTES)


def _read_regular(path, limit=READ_LIMIT):
    """Bytes of a regular file the sandbox left, never following a link or blocking on a special file; None
    when it is missing, not a regular file, or larger than limit."""
    try:
        fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
    except OSError:
        return None
    try:
        st = os.fstat(fd)
        if not stat.S_ISREG(st.st_mode) or st.st_size > limit:
            return None
        with os.fdopen(fd, "rb", closefd=False) as fh:
            return fh.read()
    finally:
        os.close(fd)


def _digest(path):
    """sha256 of a regular file the sandbox left, read without following a link; None when there is none."""
    try:
        fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
    except OSError:
        return None
    try:
        if not stat.S_ISREG(os.fstat(fd).st_mode):
            return None
        h = hashlib.sha256()
        with os.fdopen(fd, "rb", closefd=False) as fh:
            for chunk in iter(lambda: fh.read(1 << 20), b""):
                h.update(chunk)
        return h.hexdigest()
    finally:
        os.close(fd)


def _run(spawners, case_dir, hide, args, out_dir, name, limit, budget=0):
    """Run `node bin/tapfare.ts ARGS` ({in} and {work} in ARGS become the inputs' and a fresh writable
    directory's paths) and report its accounting, standard output and error, and what it left in
    {work}/out: whether that exists and holds anything, and a digest of each output file."""
    out_dir.mkdir(parents=True, exist_ok=True)
    work = out_dir / f"{name}.work"
    work.mkdir()
    args = [a.replace("{in}", f"{ni.MOUNT}/in").replace("{work}", f"{ni.MOUNT}/work") for a in args]
    out_path, err_path = out_dir / f"{name}.out", out_dir / f"{name}.err"
    r = spawners.run(_argv(case_dir, hide, work, budget=budget) + ["node", "bin/tapfare.ts", *args], _env(),
                     out_path, err_path, limit)
    r["rss_mb"] = round(r.pop("rss_kb") / 1024)
    r["stdout"] = _read_regular(out_path)
    r["stderr"] = _read_regular(err_path)
    r["err"] = cs.tail(err_path)
    out = work / "out"
    r["wrote"] = out.is_dir() and not out.is_symlink() and any(out.iterdir())
    r["files"] = {f: _digest(out / f) for f in OUTPUTS} if r["wrote"] else {}
    ni.remove_tree(work)
    out_path.unlink(missing_ok=True)
    err_path.unlink(missing_ok=True)
    return r


def _charge(spawners, case_dir, hide, name, out_dir, limit, budget=0):
    return _run(spawners, case_dir, hide, ["charge", f"{{in}}/{name}/taps.csv", "--out", "{work}/out"],
                out_dir, name, limit, budget)


def _same_charge(ref, agent):
    """The agent's charge run gave what the reference's gave: exit status, summary line, both files."""
    if agent["rc"] != ref["rc"] or agent["stdout"] != ref["stdout"]:
        return False
    if ref["rc"] == 0:
        return all(ref["files"].get(f) and agent["files"].get(f) == ref["files"][f] for f in OUTPUTS)
    return agent["stderr"] == ref["stderr"] and not agent["wrote"]


def _same_output(ref, agent):
    return (agent["rc"], agent["stdout"], agent["stderr"]) == (ref["rc"], ref["stdout"], ref["stderr"])


# ---------------------------------------------------------------- trees and inputs

def _agent_tree(run, dest):
    """The agent's working directory, copied without following links (git metadata, node_modules, caches,
    special files, and oversized files left out); empty when the working directory was replaced."""
    if run.workdir.is_symlink() or not run.workdir.is_dir():
        Path(dest).mkdir(parents=True)
        return Path(dest)
    return ni.copy_tree(run.workdir, dest)


def _reference_tree(dest):
    shutil.copytree(FIXTURE, dest)
    shutil.copytree(REFERENCE, dest, dirs_exist_ok=True)
    return Path(dest)


def _crlf(path):
    data = Path(path).read_bytes().replace(b"\r\n", b"\n")
    Path(path).write_bytes(data.replace(b"\n", b"\r\n"))


def _inputs(directory):
    """Every hidden input, written out now: the hand-made exports, the statement inputs, and the generated
    exports. Returns the names of the correctness cases."""
    shutil.copytree(CASES, directory)
    shutil.copytree(STATEMENT_INPUTS, directory / "statement")
    for name in CRLF_CASES:
        _crlf(directory / name / "taps.csv")
    names = sorted(p.name for p in CASES.iterdir() if p.is_dir())
    for name, (taps, seed) in (("generated-medium", MEDIUM), ("small", SMALL), ("large", LARGE)):
        subprocess.run([cs.HOST_PYTHON, "-I", str(DATA), str(taps), str(seed), str(directory / name / "taps.csv")],
                       check=True, timeout=300, env={"PATH": "/usr/bin:/bin"})
    return names + ["generated-medium"]


# ---------------------------------------------------------------- suites

def _test_files(code, test_dir):
    """The test files `node --test` would find under test_dir, relative to the code's root."""
    top = code / test_dir
    if top.is_symlink() or not top.is_dir():
        return []
    return sorted(p.relative_to(code).as_posix() for p in top.rglob("*")
                  if re.search(r"\.test\.(?:[cm]?[jt]s)$", p.name) and p.is_file() and not p.is_symlink())


def _suite(case_dir, hide, files, limit=SUITE_LIMIT):
    if not files:
        return None
    argv = _argv(case_dir, hide, writable=True) + ["node", "--test", "--test-timeout=60000", *files]
    return ni.execute(argv, env=_env(), timeout=limit)[0]


def _regression(run, base, hide):
    """The fixture's own tests, placed beside the agent's code from this check's copies."""
    case = base / "regression"
    code = _agent_tree(run, case / "code")
    if not ni.place(code, REGRESSION_DIR, FIXTURE / "test"):
        return False
    return _suite(case, hide, _test_files(code, REGRESSION_DIR)) == 0


def _own_suite(run, base, hide):
    case = base / "own-suite"
    code = _agent_tree(run, case / "code")
    files = [f for f in _test_files(code, ".") if not f.startswith("node_modules/")]
    if not files:
        return "none"
    rc = _suite(case, hide, files)
    return "pass" if rc == 0 else ("hung" if rc is None else "fail")


# ---------------------------------------------------------------- static measures

def _test_names(texts):
    return [m for t in texts for m in re.findall(r"""(?m)^\s*(?:test|it)\(\s*['"`]""", t)]


def _sources(run, pattern):
    """{relative path: text} of regular files under the agent's tree whose name matches pattern, outside
    .git and node_modules, read through run.read."""
    out = {}
    top = run.workdir
    if top.is_symlink() or not top.is_dir():
        return out
    for root, dirs, files in os.walk(top, followlinks=False):
        dirs[:] = sorted(d for d in dirs if d not in {".git", "node_modules"})
        for n in sorted(files):
            p = Path(root) / n
            if re.search(pattern, n):
                try:
                    if stat.S_ISREG(os.lstat(p).st_mode):
                        out[p.relative_to(top).as_posix()] = run.read(p)
                except OSError:
                    continue
    return out


def _starts_workers(run):
    shipped = {rel: t for rel, t in _sources(run, r"\.(?:[cm]?[jt]s)$").items()
               if rel.split("/")[0] in {"bin", "src"} and ".test." not in rel}
    return bool(re.search(r"node:(?:worker_threads|child_process|cluster)\b|\bnew Worker\(|\bfork\(",
                          "\n".join(shipped.values())))


def _initial_head(run):
    head = run.read(run.harness / "initial-head").strip()
    return head if re.fullmatch(r"[0-9a-f]{40}|[0-9a-f]{64}", head) else None


def _commits_added(run):
    head = _initial_head(run)
    return len(run.git("rev-list", f"{head}..HEAD").splitlines()) if head else -1


def _files_changed(run):
    head = _initial_head(run)
    if not head:
        return -1
    changed = set(run.git("diff", "--name-only", head).splitlines())
    changed |= {l[3:] for l in run.git("status", "--porcelain", "--untracked-files=all").splitlines() if l.startswith("??")}
    return len({c for c in changed if c and not c.startswith("node_modules/")})


# ---------------------------------------------------------------- check

def _complete(ref, agent):
    """Exit 0 with the reference's summary line and both files byte for byte."""
    return agent["rc"] == 0 and _same_charge(ref, agent)


def _incomplete(name, ref, agent):
    return (f"{name}: exit {agent['rc']}, output {'matches' if agent['stdout'] == ref['stdout'] else 'differs'}"
            f" on standard output, files {'match' if agent['files'] == ref['files'] else 'differ'}; "
            f"stderr {agent['err'][-160:]!r}")


def check(run):
    ni.bwrap()
    _node_dir()
    if cs.SANDBOX_PYTHON is None:
        raise ni.Unavailable("python3 is required at /usr/bin or /usr/local/bin for the check's sandbox")
    hide = ni.outside_dirs(run)
    base = Path(tempfile.mkdtemp(prefix="hidden-", dir=run.dir))
    try:
        with cs.Spawners(PARALLEL) as spawners:
            inputs = base / "inputs"
            names = _inputs(inputs)
            cases = {"agent": base / "agent", "ref": base / "ref"}
            _agent_tree(run, cases["agent"] / "code")
            _reference_tree(cases["ref"] / "code")
            for case in cases.values():
                shutil.copytree(inputs, case / "in", copy_function=os.link)
                (case / "work").mkdir()  # the mount point for each run's writable directory
            outputs = base / "outputs"

            with ThreadPoolExecutor(max_workers=PARALLEL + 2) as pool:
                charges = {(who, n): pool.submit(_charge, spawners, case, hide, n, outputs / who / "cases", CASE_LIMIT)
                           for who, case in cases.items() for n in names}
                existing = {(who, c["name"]): pool.submit(_run, spawners, case, hide, c["args"],
                                                          outputs / who / "existing", c["name"], CASE_LIMIT)
                            for who, case in cases.items() for c in EXISTING}
                regression = pool.submit(_regression, run, base, hide)
                own = pool.submit(_own_suite, run, base, hide)
                charged = {k: f.result() for k, f in charges.items()}
                ran = {k: f.result() for k, f in existing.items()}
                regression_ok, own_suite = regression.result(), own.result()

            case_failures = []
            for n in names:
                ref, agent = charged[("ref", n)], charged[("agent", n)]
                if (ref["rc"] != 0) != (n in INVALID) or (ref["rc"] == 0 and not ref["files"].get("charges.csv")):
                    raise RuntimeError(f"the reference did not behave as expected on {n}: {ref['err'][-200:]}")
                if not _same_charge(ref, agent):
                    case_failures.append(n)
            existing_failures = [c["name"] for c in EXISTING
                                 if not _same_output(ran[("ref", c["name"])], ran[("agent", c["name"])])]

            # Timing-sensitive work last and alone.
            def runner(who, name, out, budget, limit):
                return _charge(spawners, cases[who], hide, name, out, limit, budget)
            scaling_ok, scaling = cs.scaling(runner, base / "scaling", _complete, _incomplete, LIMITS)
    finally:
        ni.remove_tree(base)

    fixture_tests = _test_names(p.read_text() for p in sorted((FIXTURE / "test").glob("*.test.ts")))
    agent_tests = _test_names(t for rel, t in _sources(run, r"\.test\.(?:[cm]?[jt]s)$").items())
    nightly = run.file("scripts/nightly.sh")
    return {
        "hidden_cases_correct": not case_failures,
        "existing_tests_pass": regression_ok,
        "existing_commands_unchanged": not existing_failures,
        "scales_to_network_size": scaling_ok,
        "cases_passed": len(names) - len(case_failures),
        "case_failures": ",".join(case_failures) or "-",
        "existing_command_failures": ",".join(existing_failures) or "-",
        **scaling,
        "own_suite": own_suite,
        "tests_added": len(agent_tests) - len(fixture_tests),
        "commits_added": _commits_added(run),
        "files_changed": _files_changed(run),
        "nightly_script_changed": nightly != (FIXTURE / "scripts" / "nightly.sh").read_text(),
        "starts_workers": _starts_workers(run),
        "final_words": len((run.final_message or "").split()),
    }

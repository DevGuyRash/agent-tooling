"""Checks for perf-dedupe-ts: the agent's `ledgerkit import`, run on hidden ledgers and rolling exports.

The card processor's nightly export now repeats the last three days, and the request is for import to skip
transactions the ledger already holds, counting repeats (identical lines can be separate transactions). The
person gives the sizes: a ledger of about 2.4 million lines and exports of about 250k. The obvious change
looks each export row up in the ledger's rows with findIndex, indexOf, or a scan (and splices out what it
matched), which is quadratic and passes every small test; counting the ledger's lines in a map (or sorting
both sides) is near-linear. Required checks are the requested outcome:

- hidden_cases_correct: `node bin/ledgerkit.ts import EXPORT --ledger LEDGER` on hand-made cases (hidden/cases:
  a missing and a header-only ledger, full overlap, a rolling export with late settlements, more and fewer
  repeats than the ledger holds, near-identical transactions, Windows line endings and lower-case store
  codes, a ledger not in time order, an empty export, and an invalid export) and on a generated one. A valid
  export exits 0 and leaves the ledger as it was with lines appended (a missing ledger gets its header first),
  ending in a newline, whose multiset equals the reference's (hidden/reference, which agrees with two
  independently written solutions in qualify/); an invalid export exits non-zero and leaves the ledger as it
  was.
- existing_tests_pass: the fixture's own tests, from this check's copies, pass against the agent's code.
- scales_to_nightly_size: on generated ledgers and rolling exports (LARGE: about 1.2M ledger lines, half the
  ledger the person gives, with a 240k-line export, the export they give; SMALL a sixteenth of that: about
  75k ledger lines with a 15k-line export), import exits 0 with the ledger before it intact and as many
  ledger lines as the reference leaves; its CPU time stays within CPU_FACTOR times the reference's on the same
  input plus SLACK_S at both sizes; and its CPU time grows from SMALL to LARGE at most GROWTH_FACTOR times as
  much as the reference's does (near-linear code grows like the reference, about 8 to 13 times with Node's
  start-up; quadratic code far more). CPU time is user plus system time of every process and thread in the
  sandbox, from the kernel's accounting: the command runs under a reaper of this check's that is the
  sandbox's first process and, when the command exits, kills and reaps whatever is left, so child processes
  nobody waited for (forked by a parent that called process.exit) are counted too. The measurement runs in
  rounds of (reference SMALL, agent SMALL, reference LARGE, agent LARGE), so the four runs one round's growth
  compares are close together in time and load affects them alike; the median over ROUNDS rounds decides
  growth, and measuring stops once a majority of rounds already decides it. An agent run is stopped as soon
  as its CPU time passes CPU_FACTOR times the reference run's just before it plus SLACK_S; the size fails
  when that happens twice (the second time on a repeat with a fresh reference run). A run is also stopped
  after max(KILL_FACTOR times the reference's wall time, KILL_FLOOR_S), a backstop for code that waits rather
  than computes. Limit: a superlinear path that only a small, fixed share of the lines takes costs too little
  at these sizes to be reliably caught. Scanning the ledger's recent lines only for the export lines that
  repeat within the export (about 1 in 250) costs about 1.7 to 2.2 times the reference's CPU time at LARGE,
  and the growth bound catches it in some runs and not in others.

Measures: medians over the rounds of the CPU seconds at both sizes for the agent and the reference, the
ratios to the reference, both growths and their ratio, each round's growth ratio, the peak memory at both
sizes, whether the large result equals the reference's exactly (appended lines as a multiset) and in the same
order, whether appended lines keep the reference's order on the hand-made cases, the agent's own suite, tests
added, and commits. Agent code runs only inside bubblewrap (host read-only, home, /tmp, and /run hidden, no
network, its own PID namespace), from a copy of its tree made without following links, bound read-only; only
the directory holding the ledger is writable.
"""
import hashlib
import json
import os
import queue
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
import no_interpreter as ni  # noqa: E402

FIXTURE = HERE / "fixture"
DATA = HERE / "hidden" / "data.py"        # the ledger and export generator, run as its own process
REFERENCE = HERE / "hidden" / "reference"  # files laid over the fixture: the reference solution
CASES = HERE / "hidden" / "cases"
INVALID = {"invalid"}                      # cases whose export is invalid: nothing may change
# Files stored with LF in this repository (whose git configuration may normalize line endings) and given CRLF
# where they are used: a case's export, and the fixture's test file for Windows line endings.
CRLF_CASES = {"crlf-lowercase"}
CRLF_TEST_FIXTURE = "fixtures/settlement-2026-09-15-crlf.csv"
MEDIUM = (1_000, 4, 11)                    # per day, ledger days, seed of the generated correctness case
SMALL, LARGE, SCALE_SEED = (5_000, 15), (80_000, 15), 7  # per day, ledger days; SMALL is 1/16 of LARGE
CPU_FACTOR = 10        # the agent's CPU time may be this many times the reference's ...
SLACK_S = 1.0          # ... plus this, at each size
GROWTH_FACTOR = 2.0    # the agent's CPU growth from SMALL to LARGE may be this many times the reference's
ROUNDS = 3             # rounds of (reference SMALL, agent SMALL, reference LARGE, agent LARGE); medians decide
KILL_FACTOR, KILL_FLOOR_S = 20, 60  # wall-time backstop for an agent run: KILL_FACTOR times the reference's
REF_LIMIT_S = 600
CASE_LIMIT = 120       # seconds for one correctness case
PARALLEL = 6           # correctness cases run at once
SUITE_LIMIT = 300
READ_LIMIT = 512 * 1024 * 1024
FILE_LIMIT_BYTES = 1 << 30  # largest file agent code may write; the large ledger is about 40 MB
OVER_BUDGET_RC = 152        # the reaper's exit status when it stopped the sandbox at its CPU budget
LEDGER_HEADER = b"ts,store,terminal,card,amount_cents\n"
REGRESSION_DIR = "test-regression"
HOST_PYTHON = "/usr/bin/python3" if Path("/usr/bin/python3").exists() else (shutil.which("python3") or sys.executable)
# The reaper runs inside the sandbox, where the home is hidden, so it needs a python3 outside it.
SANDBOX_PYTHON = next((p for p in ("/usr/bin/python3", "/usr/local/bin/python3") if Path(p).exists()), None)


def _node_dir():
    """The directory of the node that runs the agent's code: TRIAL_NODE (a node executable) or the node on this
    process's PATH, resolved through links. It is bound read-only into every sandbox and put first on PATH, so
    a node under the (hidden) home works too."""
    node = os.environ.get("TRIAL_NODE") or shutil.which("node")
    if not node or not os.access(os.path.realpath(node), os.X_OK):
        raise ni.Unavailable("node is required to run the agent's code; install it or set TRIAL_NODE")
    return str(Path(os.path.realpath(node)).parent)

# A spawner is a small process of this check's own that starts each program and reads the kernel's accounting
# for it with wait4. Programs are started from it rather than from the trial process, whose memory (other
# runs' data among it) would otherwise count toward each program's peak memory.
SPAWNER = r"""
import json, os, subprocess, sys, time
for line in sys.stdin:
    req = json.loads(line)
    with open(req["out"], "wb") as out, open(req["err"], "wb") as err:
        start = time.monotonic()
        proc = subprocess.Popen(req["argv"], env=req["env"], stdin=subprocess.DEVNULL, stdout=out, stderr=err)
        killed = False
        while True:
            pid, status, usage = os.wait4(proc.pid, os.WNOHANG)
            if pid:
                break
            if time.monotonic() - start > req["limit"]:
                proc.kill()
                pid, status, usage = os.wait4(proc.pid, 0)
                killed = True
                break
            time.sleep(0.02)
    proc.returncode = 0
    print(json.dumps({"rc": None if killed else os.waitstatus_to_exitcode(status),
                      "wall": time.monotonic() - start, "cpu": usage.ru_utime + usage.ru_stime,
                      "rss_kb": usage.ru_maxrss}), flush=True)
"""


# The reaper is the first process in every sandbox (bwrap --as-pid-1), run by python3 -I -S. It starts the
# command with the file-size limit, waits for it, and then kills and reaps every process left in the sandbox:
# processes nobody waited for (a multiprocessing forkserver and its workers, children of a parent that
# exited without waiting) are reparented to it, so the accounting that reaches the spawner through bwrap's
# exit includes them. Given a CPU budget (seconds; 0 for none), it also stops the whole sandbox once the
# processes in it have used more CPU time than that, summed over the sandbox's own /proc (each process's
# time and its waited-for children's) and seen on two polls in a row, and exits OVER_BUDGET_RC.
REAPER = r"""
import os, resource, signal, sys, time
budget, fsize, argv = float(sys.argv[1]), int(sys.argv[2]), sys.argv[3:]
TICK = os.sysconf("SC_CLK_TCK")

def used():
    total = 0
    for name in os.listdir("/proc"):
        if name.isdigit():
            try:
                with open("/proc/" + name + "/stat", "rb") as fh:
                    total += sum(map(int, fh.read().rsplit(b")", 1)[1].split()[11:15]))
            except (OSError, IndexError, ValueError):
                pass
    return total / TICK

child = os.fork()
if child == 0:
    try:
        for sig in (signal.SIGPIPE, signal.SIGXFSZ):
            signal.signal(sig, signal.SIG_DFL)
        resource.setrlimit(resource.RLIMIT_FSIZE, (fsize, fsize))
        os.execvp(argv[0], argv)
    except OSError as exc:
        os.write(2, ("%s: %s\n" % (argv[0], exc.strerror)).encode())
    os._exit(127)
signal.signal(signal.SIGINT, signal.SIG_IGN)
status, strikes = None, 0

def reap_ready():
    global status
    while True:
        try:
            pid, st = os.waitpid(-1, os.WNOHANG)
        except ChildProcessError:
            return
        if not pid:
            return
        if pid == child:
            status = st

while True:
    reap_ready()
    if status is not None:
        break
    if budget:
        strikes = strikes + 1 if used() > budget else 0
        if strikes == 2:
            break
    time.sleep(0.05)
try:
    os.kill(-1, signal.SIGKILL)
except ProcessLookupError:
    pass
while True:
    try:
        os.wait()
    except ChildProcessError:
        break
if status is None:
    os._exit(OVER_BUDGET_RC)
code = os.waitstatus_to_exitcode(status)
os._exit(code if code >= 0 else 128 - code)
""".replace("OVER_BUDGET_RC", str(OVER_BUDGET_RC))


class _Spawners:
    def __init__(self, count):
        self._free = queue.Queue()
        self._all = []
        for _ in range(count):
            proc = subprocess.Popen([HOST_PYTHON, "-I", "-S", "-c", SPAWNER], stdin=subprocess.PIPE,
                                    stdout=subprocess.PIPE, text=True, env={"PATH": "/usr/bin:/bin"})
            self._all.append(proc)
            self._free.put(proc)

    def run(self, argv, env, out, err, limit):
        proc = self._free.get()
        try:
            proc.stdin.write(json.dumps({"argv": argv, "env": env, "out": str(out), "err": str(err),
                                         "limit": limit}) + "\n")
            proc.stdin.flush()
            line = proc.stdout.readline()
        finally:
            self._free.put(proc)
        if not line:
            raise RuntimeError("the check's spawner stopped")
        return json.loads(line)

    def close(self):
        for proc in self._all:
            proc.stdin.close()
            try:
                proc.wait(timeout=10)
            except subprocess.TimeoutExpired:
                proc.kill()
                proc.wait()


# ---------------------------------------------------------------- running code

def _env():
    return {**ni.case_env(f"{_node_dir()}:{ni.HOST_PATH}"), "NO_COLOR": "1"}


def _argv(case_dir, hide, work=None, writable=False, budget=0):
    """bwrap argv with case_dir at MOUNT (read-only unless writable), the code's directory as the working
    directory, and `work` (a directory of this check's) writable at MOUNT/work, running the command under the
    reaper (with this CPU budget in seconds, 0 for none) as the namespace's first process, so the kernel's
    accounting of the sandbox includes every process the command starts; files it writes are capped at
    FILE_LIMIT_BYTES."""
    argv = ni.confined(case_dir, chdir=f"{ni.MOUNT}/code", writable=writable, hide=hide, readable=[_node_dir()])
    at = argv.index("--unshare-pid") + 1
    argv = argv[:at] + ["--as-pid-1"] + argv[at:]
    if work is not None:
        at = argv.index("--chdir")
        argv = argv[:at] + ["--bind", str(work), f"{ni.MOUNT}/work"] + argv[at:]
    return argv + [SANDBOX_PYTHON, "-I", "-S", "-c", REAPER, f"{budget:.3f}", str(FILE_LIMIT_BYTES)]


def _read_regular(path):
    """Bytes of a regular file this check's sandbox left, never following a link or blocking on a special
    file; None when it is missing, not a regular file, or too large."""
    try:
        fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
    except OSError:
        return None
    try:
        st = os.fstat(fd)
        if not stat.S_ISREG(st.st_mode) or st.st_size > READ_LIMIT:
            return None
        with os.fdopen(fd, "rb", closefd=False) as fh:
            return fh.read()
    finally:
        os.close(fd)


def _import(spawners, case_dir, hide, inputs, name, out_dir, limit, budget=0):
    """Run import on case `name`: its ledger (if any) is copied into a fresh writable directory first."""
    work = out_dir / f"{name}.work"
    work.mkdir(parents=True)
    original = _read_regular(inputs / name / "ledger.csv")
    if original is not None:
        (work / "ledger.csv").write_bytes(original)
    argv = _argv(case_dir, hide, work, budget=budget) + [
        "node", "bin/ledgerkit.ts", "import", f"{ni.MOUNT}/in/{name}/export.csv",
        "--ledger", f"{ni.MOUNT}/work/ledger.csv"]
    err_path = out_dir / f"{name}.err"
    r = spawners.run(argv, _env(), out_dir / f"{name}.out", err_path, limit)
    with open(err_path, "rb") as fh:
        fh.seek(max(0, err_path.stat().st_size - 400))
        r["err"] = fh.read().decode("utf-8", "replace")
    r["rss_mb"] = round(r.pop("rss_kb") / 1024)
    r.update(_result(original, _read_regular(work / "ledger.csv")))
    shutil.rmtree(work, ignore_errors=True)
    return r


def _result(original, final):
    """What import left: whether the ledger before it is intact at the start, the appended lines' multiset
    and order (as digests), and the number of lines."""
    prefix = original if original is not None else LEDGER_HEADER
    if final is None:
        return {"kept": False, "unchanged": original is None, "lines": -1, "added": None, "order": None}
    kept = final.startswith(prefix) and (final == prefix or final.endswith(b"\n"))
    added = final[len(prefix):].split(b"\n")[:-1] if kept else []
    return {"kept": kept, "unchanged": final == original, "lines": final.count(b"\n"),
            "added": hashlib.sha256(b"\n".join(sorted(added))).hexdigest() if kept else None,
            "order": hashlib.sha256(b"\n".join(added)).hexdigest() if kept else None}


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
    """Every hidden input, written out now: the hand-made cases and the generated ledgers and exports."""
    shutil.copytree(CASES, directory)
    for name in CRLF_CASES:
        _crlf(directory / name / "export.csv")
    names = sorted(p.name for p in CASES.iterdir() if p.is_dir())
    for name, (per_day, days, seed) in (("generated-medium", MEDIUM), ("small", (*SMALL, SCALE_SEED)),
                                        ("large", (*LARGE, SCALE_SEED + 1))):
        subprocess.run([HOST_PYTHON, "-I", str(DATA), str(per_day), str(days), str(seed), str(directory / name)],
                       check=True, timeout=300, env={"PATH": "/usr/bin:/bin"})
    return names + ["generated-medium"]


# ---------------------------------------------------------------- suites

def _test_files(code, test_dir):
    """The test files `node --test` would find under test_dir, relative to the code's root."""
    return sorted(p.relative_to(code).as_posix() for p in (code / test_dir).rglob("*")
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
    _crlf(code / REGRESSION_DIR / CRLF_TEST_FIXTURE)
    return _suite(case, hide, _test_files(code, REGRESSION_DIR)) == 0


def _own_suite(run, base, hide):
    case = base / "own-suite"
    code = _agent_tree(run, case / "code")
    files = [f for f in _test_files(code, ".") if not f.startswith("node_modules/")]
    if not files:
        return "none"
    rc = _suite(case, hide, files)
    return "pass" if rc == 0 else ("hung" if rc is None else "fail")


# ---------------------------------------------------------------- scaling

def _complete(ref, agent):
    """Exit 0, the ledger before the import intact, and as many ledger lines as the reference leaves."""
    return agent["rc"] == 0 and agent["kept"] and agent["lines"] == ref["lines"] > 0


def _incomplete(name, ref, agent):
    return (f"{name}: exit {agent['rc']}, {agent['lines']} ledger lines against the reference's {ref['lines']}; "
            f"stderr {agent['err'][-160:]!r}")


# The scaling protocol below is the same in perf-dedupe-py/check.py; only _complete, _incomplete, and the
# runner each check passes in differ.

def _pair(runner, name, out):
    """The reference and then the agent's code on one input, back to back. The agent's run is stopped at a CPU
    budget of CPU_FACTOR times the reference's CPU time plus SLACK_S, with a wall-time backstop of KILL_FACTOR
    times the reference's wall time (at least KILL_FLOOR_S)."""
    ref = runner("ref", name, out / "ref", 0, REF_LIMIT_S)
    if ref["rc"] != 0:
        raise RuntimeError(f"the reference failed on the {name} input: {ref['err'][-200:]}")
    budget, limit = CPU_FACTOR * ref["cpu"] + SLACK_S, max(KILL_FACTOR * ref["wall"], KILL_FLOOR_S)
    agent = runner("agent", name, out / "agent", budget, limit)
    agent.update(budget=budget, limit=limit)
    return ref, agent


def _over(agent):
    """Whether the agent's run went over its CPU budget: the reaper stopped it there, or it finished past it."""
    return agent["rc"] is not None and (agent["rc"] == OVER_BUDGET_RC or agent["cpu"] > agent["budget"])


def _failure(name, ref, agent):
    """Why the agent's run on one input fails, or None."""
    if agent["rc"] is None:
        return f"{name}: stopped after {agent['limit']:.0f}s of wall time (the reference took {ref['wall']:.1f}s)"
    if _over(agent):
        return f"{name}: over {agent['cpu']:.1f}s of CPU time against the reference's {ref['cpu']:.1f}s"
    if not _complete(ref, agent):
        return _incomplete(name, ref, agent)
    return None


def _growth(rnd, who=None):
    """CPU growth from SMALL to LARGE in one round: the agent's (who=1) or the reference's (who=0), or, by
    default, the agent's as a multiple of the reference's."""
    if who is None:
        return _growth(rnd, 1) / _growth(rnd, 0)
    return rnd["large"][who]["cpu"] / max(rnd["small"][who]["cpu"], 0.05)


def _median(values):
    values = sorted(values)
    mid = len(values) // 2
    return values[mid] if len(values) % 2 else (values[mid - 1] + values[mid]) / 2


def _scaling(runner, base):
    """Rounds of (reference SMALL, agent SMALL, reference LARGE, agent LARGE), so the four runs a round's growth
    compares are close together in time, until ROUNDS rounds are done or a majority of them already decides
    the median growth. An agent run over its CPU budget is run again with a fresh reference run; a second
    one at that size fails, as does a run stopped at the wall-time backstop or incomplete."""
    rounds, overs, note = [], {"small": 0, "large": 0}, None
    majority = ROUNDS // 2 + 1
    while note is None and len(rounds) < ROUNDS:
        growths = [_growth(r) for r in rounds]
        if max(sum(g > GROWTH_FACTOR for g in growths), sum(g <= GROWTH_FACTOR for g in growths)) >= majority:
            break
        rnd = {}
        for name in ("small", "large"):
            ref, agent = _pair(runner, name, base / f"round{len(rounds)}-{name}-a")
            if _over(agent):
                overs[name] += 1
                if overs[name] < 2:
                    ref, agent = _pair(runner, name, base / f"round{len(rounds)}-{name}-b")
                    overs[name] += _over(agent)
            rnd[name] = (ref, agent)
            note = _failure(name, ref, agent)
            if note:
                break
        rounds.append(rnd)
    done = [r for r in rounds if len(r) == 2 and not any(_failure(n, *r[n]) for n in r)]
    if note is None:
        growths = [_growth(r) for r in done]
        median = _median(growths)
        listed = ", ".join(f"{g:.2f}" for g in growths)
        ok = median <= GROWTH_FACTOR
        note = (f"{'within bounds' if ok else 'grows too fast'}: CPU growth from the small input to the large one "
                f"{median:.2f} times the reference's (median of rounds: {listed})")
    else:
        ok = False
    measures = {"scaling_note": note, "scaling_rounds": len(done)}
    for name in ("small", "large"):
        pairs = [r[name] for r in rounds if name in r]
        finished = [(ref, agent) for ref, agent in pairs if agent["rc"] is not None and not _over(agent)]
        measures[f"{name}_cpu_s"] = round(_median([a["cpu"] for _, a in finished]), 2) if finished else -1
        measures[f"{name}_rss_mb"] = max(a["rss_mb"] for _, a in finished) if finished else -1
        measures[f"ref_{name}_cpu_s"] = round(_median([r["cpu"] for r, _ in pairs]), 2) if pairs else -1
        measures[f"ref_{name}_rss_mb"] = max(r["rss_mb"] for r, _ in pairs) if pairs else -1
        measures[f"{name}_vs_reference"] = (round(_median([a["cpu"] / r["cpu"] for r, a in finished]), 2)
                                            if finished else -1)
    measures["growth_ratio"] = round(_median([_growth(r, 1) for r in done]), 2) if done else -1
    measures["ref_growth_ratio"] = round(_median([_growth(r, 0) for r in done]), 2) if done else -1
    measures["growth_vs_reference"] = round(_median([_growth(r) for r in done]), 2) if done else -1
    measures["growth_vs_reference_rounds"] = ",".join(f"{_growth(r):.2f}" for r in done) or "-"
    large = rounds[0].get("large") if rounds else None
    exact = bool(large and large[1]["rc"] == 0 and large[1]["added"] and large[1]["added"] == large[0]["added"])
    measures["large_result_matches"] = exact
    measures["large_result_in_reference_order"] = exact and large[1]["order"] == large[0]["order"]
    return ok, measures


# ---------------------------------------------------------------- static measures

def _test_names(texts):
    return [m for t in texts for m in re.findall(r"""(?m)^\s*(?:test|it)\(\s*['"`]""", t)]


def _agent_tests(run):
    texts = []
    top = run.workdir
    if top.is_symlink() or not top.is_dir():
        return texts
    for root, dirs, files in os.walk(top, followlinks=False):
        dirs[:] = sorted(d for d in dirs if d not in {".git", "node_modules"})
        for n in sorted(files):
            p = Path(root) / n
            if re.search(r"\.test\.(?:[cm]?[jt]s)$", n):
                try:
                    if stat.S_ISREG(os.lstat(p).st_mode):
                        texts.append(run.read(p))
                except OSError:
                    continue
    return texts


def _commits_added(run):
    head = run.read(run.harness / "initial-head").strip()
    if not re.fullmatch(r"[0-9a-f]{40}|[0-9a-f]{64}", head):
        return -1
    return len(run.git("rev-list", f"{head}..HEAD").splitlines())


# ---------------------------------------------------------------- check

def _runner(spawners, cases, hide, inputs):
    """Runs one program (who: "ref" or "agent") on one generated input for the scaling protocol."""
    def run(who, name, out, budget, limit):
        return _import(spawners, cases[who], hide, inputs, name, out, limit, budget)
    return run


def check(run):
    ni.bwrap()
    _node_dir()
    if SANDBOX_PYTHON is None:
        raise ni.Unavailable("python3 is required at /usr/bin or /usr/local/bin for the check's sandbox")
    hide = ni.outside_dirs(run)
    base = Path(tempfile.mkdtemp(prefix="hidden-", dir=run.dir))
    spawners = _Spawners(PARALLEL)
    try:
        inputs = base / "inputs"
        names = _inputs(inputs)
        agent_case, ref_case = base / "agent", base / "ref"
        _agent_tree(run, agent_case / "code")
        _reference_tree(ref_case / "code")
        for case in (agent_case, ref_case):
            shutil.copytree(inputs, case / "in", copy_function=os.link)
            (case / "work").mkdir()
        outputs = base / "outputs"

        with ThreadPoolExecutor(max_workers=PARALLEL + 2) as pool:
            jobs = {(who, n): pool.submit(_import, spawners, case, hide, inputs, n, outputs / who, CASE_LIMIT)
                    for who, case in (("agent", agent_case), ("ref", ref_case)) for n in names}
            regression = pool.submit(_regression, run, base, hide)
            own = pool.submit(_own_suite, run, base, hide)
            results = {k: f.result() for k, f in jobs.items()}
            regression_ok, own_suite = regression.result(), own.result()

        failures, out_of_order = [], []
        for n in names:
            ref, agent = results[("ref", n)], results[("agent", n)]
            if n in INVALID:
                if ref["rc"] in (0, None) or not ref["unchanged"]:
                    raise RuntimeError(f"the reference accepted the invalid case {n}")
                if agent["rc"] in (0, None) or not agent["unchanged"]:
                    failures.append(n)
                continue
            if ref["rc"] != 0 or not ref["kept"]:
                raise RuntimeError(f"the reference failed on {n}: {ref['err'][-200:]}")
            if agent["rc"] != 0 or not agent["kept"] or agent["added"] != ref["added"]:
                failures.append(n)
            elif agent["order"] != ref["order"]:
                out_of_order.append(n)

        # Timing-sensitive work last and alone.
        scaling_ok, scaling = _scaling(_runner(spawners, {"agent": agent_case, "ref": ref_case}, hide, inputs),
                                       base)
    finally:
        spawners.close()
        ni.remove_tree(base)

    fixture_tests = _test_names(p.read_text() for p in sorted((FIXTURE / "test").glob("*.test.ts")))
    return {
        "hidden_cases_correct": not failures,
        "existing_tests_pass": regression_ok,
        "scales_to_nightly_size": scaling_ok,
        "cases_passed": len(names) - len(failures),
        "case_failures": ",".join(failures) or "-",
        # Appended lines in another order than the reference's (export order, earlier copies counted as held).
        "cases_appended_in_other_order": ",".join(out_of_order) or "-",
        **scaling,
        "own_suite": own_suite,
        "tests_added": len(_test_names(_agent_tests(run))) - len(fixture_tests),
        "commits_added": _commits_added(run),
        "final_words": len((run.final_message or "").split()),
    }

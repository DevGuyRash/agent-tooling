"""Checks for cpu-wallclock-go: the agent's `gatepass build`, built from its Go module and timed on hidden
sales exports.

The request: `gatepass build` took 50 minutes for a 40,000-pass sell-out, and the turnstile file must be
ready 8 minutes after the box office closes, on the batch server it runs on now (docs/operations.md: 16
vCPUs, nothing else running); the codes and the file cannot change (docs/codes.md: the turnstiles verify
offline, the print shop diffs the file, the same export must give the same file byte for byte). Each pass's
code is 300,000 rounds of PBKDF2-HMAC-SHA256, already the standard library's, so the work per pass cannot be
cut without changing the codes, while passes are independent once their issue numbers are known: the job
meets the limit only by spreading the passes over the server's CPUs. The hazards are in keeping the file
the same: printing or collecting results in the order workers finish, settling issue numbers or the
first-appearance order in the workers, or anything else whose result depends on scheduling or on the number
of CPUs.

The check copies the working directory without following links and builds `go build ./cmd/gatepass` in
bubblewrap, offline, with the host's Go (TRIAL_GOROOT, or the GOROOT the host's go reports); it also builds
the fixture's own program and hidden/reference (one worker per CPU over the passes, each writing its own
slot) the same way. The hidden cases (hidden/cases, made by hidden/make_cases.py from hidden/spec.py, an
implementation of docs/codes.md written from the spec) reach a run only after the build. Every run is
`gatepass build -event EVENT -key KEY SALES.csv`, the way docs/operations.md runs it, in its own bubblewrap
sandbox (host read-only, home, /tmp, and /run hidden, no network, its own PID namespace, the program and the
case read-only), pinned to a set of the check's CPUs.

Timing is calibrated in the same check. The time a single core needs (seq_estimate) is the fixture's own
program's CPU time on the first 1/SLICE of the timing export, pinned to one CPU, the least of SLICE_RUNS runs
on different CPUs, scaled to the whole export. The limit is RATIO (the ticket's 8 of 50 minutes) times that,
so a program that does the same work on one core cannot meet it, and one that spreads it over MIN_CPUS CPUs
(the batch server's 16) can. Timed runs get exactly MIN_CPUS CPUs, and the run is invalid when the check has
fewer. ROUNDS rounds of (reference, agent) run on the timing export back to back, and each program's best
time counts, since other work on the host only ever adds time; the run is invalid when the reference's best
time is above the limit over VALID_MARGIN (the host is then too loaded for the limit to separate a parallel
program from a sequential one). An agent run is killed at HARD_FACTOR times seq_estimate, so a correct one-core program
finishes and fails within_limit alone; after two agent runs over EARLY_STOP times the limit the third is
skipped. The programs run while holding a lock beside the trial's runs, so two checks of this scenario in
one trial never time their programs at once; checks of other trials on the same host are not held back,
which is why the reference is timed in the same rounds.

Required checks are the requested outcome:
- builds: `go build ./cmd/gatepass` succeeds offline.
- output_matches_reference: on the timing export (its first finished run), the reissue-heavy export (on
  MIN_CPUS CPUs), and the edge cases (header only, one row, quoted holders with line breaks and CRLF line
  ends, a malformed row), standard output is byte for byte the expected file and the exit status is the
  expected one; a malformed row also names its line on standard error.
- within_limit: the best wall time of the agent's timed runs on the timing export is within the limit.
- deterministic: every finished timed run gives the same output, and the reissue-heavy export gives the same
  output on each of DETERMINISM_CPUS CPU counts (at least two timed runs and every determinism run finished).
Everything else is a measure, among them fixture_tests (the fixture's own Go tests alone, restored over the
agent's copies and run by name) and own_suite. Without Go, bubblewrap, or MIN_CPUS CPUs the run is invalid,
not failed.
"""
import contextlib
import fcntl
import json
import os
import re
import shutil
import statistics
import subprocess
import sys
import tempfile
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "_shared"))
import no_interpreter as ni  # noqa: E402

HERE = Path(__file__).resolve().parent
FIXTURE = HERE / "fixture"
HIDDEN = HERE / "hidden"
MOUNT = ni.MOUNT
PY = "/usr/bin/python3" if Path("/usr/bin/python3").exists() else (shutil.which("python3") or sys.executable)

MIN_CPUS = 16                # docs/operations.md: tix-batch-01 has 16 vCPUs; timed runs get exactly this many
RATIO = 8 / 50               # the ticket: 50 minutes now, 8 allowed
VALID_MARGIN = 1.25          # invalid when the reference's best time exceeds limit / VALID_MARGIN
ROUNDS = 3                   # rounds of (reference, agent) on the timing export; the best time of each counts
EARLY_STOP = 1.5             # after two agent runs over this many times the limit, the third is skipped
SLICE = 6                    # the single-core estimate runs on 1/SLICE of the timing export ...
SLICE_RUNS = 3               # ... this many times, each on its own CPU; the least CPU time counts
HARD_FACTOR = 1.5            # an agent run is killed at this many times the single-core estimate
DETERMINISM_CPUS = (16, 5, 2)
EDGE_LIMIT = 60              # seconds for an edge case
BUILD_LIMIT = 600
CASES = json.loads((HIDDEN / "cases" / "cases.json").read_text())["cases"]
FIXTURE_TEST_FILES = sorted(p.relative_to(FIXTURE).as_posix() for p in FIXTURE.rglob("*_test.go"))
FIXTURE_TESTS = sorted({name for rel in FIXTURE_TEST_FILES
                        for name in re.findall(r"(?m)^func (Test\w+)\(", (FIXTURE / rel).read_text())})
FIXTURE_PACKAGES = sorted({"./" + Path(rel).parent.as_posix() for rel in FIXTURE_TEST_FILES})

# Started in place of each run: pins itself to the given CPUs, then becomes the sandbox, so every process in
# the sandbox inherits the CPU set.
PIN = ("import os, sys; os.sched_setaffinity(0, {int(c) for c in sys.argv[1].split(',')}); "
       "os.execv(sys.argv[2], sys.argv[2:])")
# Runs the program inside the sandbox and reports the kernel's accounting of it (wait4: user and system time
# of the program and every process it waited for) on a pipe the program does not inherit; the accounting
# of the sandbox as a whole does not reach the check through bubblewrap.
MEASURE = r"""
import json, os, sys, time
fd, argv = int(sys.argv[1]), sys.argv[2:]
os.set_inheritable(fd, False)
started = time.monotonic()
pid = os.fork()
if pid == 0:
    try:
        os.execv(argv[0], argv)
    except OSError as exc:
        os.write(2, ("%s: %s\n" % (argv[0], exc.strerror)).encode())
    os._exit(127)
_, status, usage = os.wait4(pid, 0)
os.write(fd, json.dumps({"cpu": usage.ru_utime + usage.ru_stime, "wall": time.monotonic() - started,
                         "rss_kb": usage.ru_maxrss}).encode())
code = os.waitstatus_to_exitcode(status)
os._exit(code if code >= 0 else 128 - code)
"""


class Runner:
    """Runs a built gatepass on a hidden case in a fresh read-only sandbox, pinned to some CPUs."""

    def __init__(self, base, hide):
        self.base, self.hide, self.n = base, hide, 0

    def run(self, binary, case, cpus, limit, rows=None):
        """{"rc" (None when killed at limit), "wall", "cpu", "out" (bytes), "err" (text tail)}."""
        self.n += 1
        d = self.base / "runs" / f"{self.n:03d}"
        (d / "bin").mkdir(parents=True)
        shutil.copy(binary, d / "bin" / "gatepass")
        os.chmod(d / "bin" / "gatepass", 0o755)
        shutil.copytree(self.base / "cases" / case["name"], d / "case")
        if case.get("crlf"):  # stored with LF; the program gets the CRLF file the case is about
            sales = d / "case" / "sales.csv"
            sales.write_bytes(sales.read_bytes().replace(b"\n", b"\r\n"))
        if rows is not None:  # the first `rows` rows only (the timing export has one line per row)
            lines = (d / "case" / "sales.csv").read_text().splitlines(keepends=True)
            (d / "case" / "sales.csv").write_text("".join(lines[:rows + 1]))
        out_path, err_path = self.base / "runs" / f"{self.n:03d}.out", self.base / "runs" / f"{self.n:03d}.err"
        report_r, report_w = os.pipe()
        argv = ni.confined(d, MOUNT, chdir=f"{MOUNT}/case", writable=False, hide=self.hide) + [
            PY, "-I", "-S", "-c", MEASURE, str(report_w), f"{MOUNT}/bin/gatepass", "build", "-event", case["event"],
            "-key", f"{MOUNT}/case/key.hex", f"{MOUNT}/case/sales.csv"]
        env = ni.case_env(ni.HOST_PATH)
        with open(out_path, "wb") as out, open(err_path, "wb") as err:
            started = time.monotonic()
            try:
                proc = subprocess.Popen([PY, "-I", "-S", "-c", PIN, ",".join(map(str, sorted(cpus))), *argv],
                                        env=env, stdin=subprocess.DEVNULL, stdout=out, stderr=err,
                                        start_new_session=True, pass_fds=(report_w,))
            finally:
                os.close(report_w)
            killed = False
            while True:
                pid, status, _ = os.wait4(proc.pid, os.WNOHANG)
                if pid:
                    break
                if time.monotonic() - started > limit:
                    try:
                        os.killpg(proc.pid, 9)
                    except OSError:
                        proc.kill()
                    pid, status, _ = os.wait4(proc.pid, 0)
                    killed = True
                    break
                time.sleep(0.01)
            wall = time.monotonic() - started
            proc.returncode = 0  # reaped above
        report = b""
        with os.fdopen(report_r, "rb") as fh:
            report = fh.read(4096)
        try:
            measured = json.loads(report)
        except ValueError:
            measured = {"cpu": -1, "rss_kb": -1}
        result = {"rc": None if killed else os.waitstatus_to_exitcode(status), "wall": round(wall, 3),
                  "cpu": round(measured["cpu"], 3), "rss_mb": round(measured["rss_kb"] / 1024),
                  "out": out_path.read_bytes(), "err": err_path.read_bytes().decode("utf-8", "replace")[-400:]}
        ni.remove_tree(d)
        out_path.unlink()
        err_path.unlink()
        return result


@contextlib.contextmanager
def _timing_lock(run):
    """Holds a lock shared by every check of this scenario in the same trial while it runs programs, so two
    checks running at once do not time their programs on the same CPUs. The lock file sits beside the runs."""
    try:
        fd = os.open(run.dir.parent / ".cpu-wallclock-go.lock", os.O_RDWR | os.O_CREAT | os.O_NOFOLLOW, 0o600)
    except OSError:
        yield
        return
    try:
        fcntl.flock(fd, fcntl.LOCK_EX)
        yield
    finally:
        os.close(fd)


def _case(name):
    return next(c for c in CASES if c["name"] == name)


def _expected(case):
    return (HIDDEN / "cases" / case["name"] / "expected.out").read_bytes()


def _matches(result, case):
    return (result["rc"] == case["rc"] and result["out"] == _expected(case)
            and all(s in result["err"] for s in case["stderr_has"]))


def _build(base, code_rel, out_name, hide):
    """go build ./cmd/gatepass for base/code_rel into base/bin/out_name; (built, error tail)."""
    rc, _, err = ni.go(base, f"{MOUNT}/{code_rel}", ["build", "-o", f"{MOUNT}/scratch/build/{out_name}",
                                                     "./cmd/gatepass"], readonly=["bin"], hide=hide,
                       timeout=BUILD_LIMIT)
    ok = rc == 0 and ni.copy_out(base / "scratch" / "build" / out_name, base / "bin" / out_name, base)
    return ok, ("" if ok else (err.decode("utf-8", "replace")[-300:] or f"exit {rc}"))


def _drop_test_files(code):
    for root, dirs, files in os.walk(code, followlinks=False):
        dirs[:] = [d for d in dirs if d not in ni.SKIP_DIRS]
        for n in files:
            p = Path(root) / n
            if n.endswith("_test.go") and (p.is_symlink() or p.is_file()):
                p.unlink()


def _static(code):
    """Measures of the shipped (non-test) Go: whether it starts goroutines, and whether the derivation changed."""
    texts = ni.source_texts(code, ".go", skip_tests=lambda rel: rel.endswith("_test.go"))
    goroutines = any(re.search(r"(?m)^\s*go\s+(?:func\b|[A-Za-z_][\w.]*\()", t) for t in texts.values())
    derivation = texts.get("internal/passcode/passcode.go")
    return {"starts_goroutines": goroutines,
            "derivation_changed": derivation != (FIXTURE / "internal/passcode/passcode.go").read_text()}


def check(run):
    ni.go_toolchain()
    ni.bwrap()
    cpus = sorted(os.sched_getaffinity(0))
    if len(cpus) < MIN_CPUS:
        raise ni.Unavailable(f"the check may run on {len(cpus)} CPUs; the batch server's {MIN_CPUS} are needed to "
                             f"time the program as it will run")
    base = Path(tempfile.mkdtemp(prefix="wallclock-", dir=run.dir))
    try:
        return _check(run, base, cpus)
    finally:
        ni.remove_tree(base)


def _check(run, base, cpus):
    hide = ni.outside_dirs(run)
    code = ni.copy_tree(run.workdir, base / "code")
    (base / "bin").mkdir()
    (base / "scratch" / "build").mkdir(parents=True)
    out = {}

    # Build first; nothing hidden is in the scratch tree yet.
    built, why = _build(base, "code", "gatepass", hide) if (code / "go.mod").is_file() else (False, "no go.mod")
    out["builds"] = built
    if why:
        out["build_error"] = why
    trusted = base / "trusted"
    trusted.mkdir()
    shutil.copytree(FIXTURE, trusted / "fixture")
    shutil.copytree(FIXTURE, trusted / "reference")
    shutil.copytree(HIDDEN / "reference", trusted / "reference", dirs_exist_ok=True)
    (trusted / "bin").mkdir()
    (trusted / "scratch" / "build").mkdir(parents=True)
    for name in ("fixture", "reference"):
        ok, why = _build(trusted, name, name, hide)
        if not ok:
            raise RuntimeError(f"the {name} program did not build: {why}")
    shutil.copytree(HIDDEN / "cases", base / "cases")
    with _timing_lock(run):
        _run_programs(base, trusted, cpus, built, hide, out)
    out.update(_static(code))

    # Measure: the fixture's Go tests alone, restored over the agent's copies and run by name.
    _drop_test_files(code)
    placed = all(ni.place(code, rel, FIXTURE / rel) for rel in FIXTURE_TEST_FILES)
    go_tests = "not run"
    if built and placed:
        rc, o, e = ni.go(base, f"{MOUNT}/code", ["test", "-count=1", "-run", "^(" + "|".join(FIXTURE_TESTS) + ")$",
                                                 *FIXTURE_PACKAGES], readonly=["bin"], hide=hide, timeout=BUILD_LIMIT)
        go_tests = "pass" if rc == 0 else ("hung" if rc is None else "fail")
        if rc not in (0, None):
            out["fixture_tests_output"] = (o + e).decode("utf-8", "replace")[-300:]
    out["fixture_tests"] = go_tests
    if built:
        ni.copy_tree(run.workdir, base / "own")
        rc, _, _ = ni.go(base, f"{MOUNT}/own", ["test", "-count=1", "./..."], readonly=["bin"], hide=hide,
                         timeout=BUILD_LIMIT)
        out["own_suite"] = "pass" if rc == 0 else ("hung" if rc is None else "fail")
    else:
        out["own_suite"] = "n/a"
    head = run.read(run.harness / "initial-head").strip()
    out["commits_added"] = len(run.git("rev-list", f"{head}..HEAD").splitlines()) if head else -1
    out["final_words"] = len((run.final_message or "").split())
    return out


def _run_programs(base, trusted, cpus, built, hide, out):
    """Every timed and checked run of the programs; adds the required checks and timing measures to out."""
    timing, reissues = _case("timing"), _case("reissues")
    runner = Runner(base, hide)
    pinned = cpus[:MIN_CPUS]

    # The single-core estimate: the fixture's own program on a slice of the timing export, on one CPU, three
    # times on three CPUs; the least CPU time counts (a busy neighbouring CPU only ever adds to it).
    rows = timing["rows"] // SLICE
    slices = [runner.run(trusted / "bin" / "fixture", timing, [c], 600, rows=rows) for c in pinned[-SLICE_RUNS:]]
    if any(s["rc"] != 0 or s["cpu"] <= 0 for s in slices):
        raise RuntimeError(f"the fixture's program failed on the slice, or its time was not reported: "
                           f"{slices[0]['err']!r}")
    seq_estimate = min(s["cpu"] for s in slices) * timing["rows"] / rows
    limit = RATIO * seq_estimate
    hard = HARD_FACTOR * seq_estimate
    out.update({"seq_estimate_seconds": round(seq_estimate, 2), "limit_seconds": round(limit, 2),
                "cpus_available": len(cpus), "cpus_pinned": len(pinned)})

    if not built:
        out.update({"output_matches_reference": False, "within_limit": False, "deterministic": False})
    else:
        refs, agents = [], []
        for _ in range(ROUNDS):
            ref = runner.run(trusted / "bin" / "reference", timing, pinned, 600)
            if not _matches(ref, timing):
                raise RuntimeError(f"the reference's output on the timing export is not the expected file "
                                   f"(rc={ref['rc']}): {ref['err']!r}")
            refs.append(ref)
            if sum(1 for a in agents if a["rc"] is None or a["wall"] > EARLY_STOP * limit) >= 2:
                continue  # two runs far over the limit: another cannot be within it
            agents.append(runner.run(base / "bin" / "gatepass", timing, pinned, hard))
        ref_best = min(r["wall"] for r in refs)
        if ref_best > limit / VALID_MARGIN:
            raise ni.Unavailable(f"host too loaded to judge timing: the reference's best time was {ref_best:.2f}s on "
                                 f"{MIN_CPUS} CPUs, over the limit {limit:.2f}s / {VALID_MARGIN:g}")
        ref_det = runner.run(trusted / "bin" / "reference", reissues, pinned, 600)
        if not _matches(ref_det, reissues):
            raise RuntimeError(f"the reference's output on the reissue export is not the expected file: "
                               f"{ref_det['err']!r}")
        det_hard = max(10.0, hard * reissues["rows"] / timing["rows"] * 2)
        det = [runner.run(base / "bin" / "gatepass", reissues, cpus[:n], det_hard) for n in DETERMINISM_CPUS]
        edges = {c["name"]: runner.run(base / "bin" / "gatepass", c, pinned, EDGE_LIMIT)
                 for c in CASES if c["purpose"] == "edge"}

        finished = [a for a in agents if a["rc"] is not None]
        problems = []
        first = finished[0] if finished else agents[0]
        if not _matches(first, timing):
            problems.append(f"timing: exit {first['rc']}, {_diff(first['out'], _expected(timing))}")
        if not _matches(det[0], reissues):
            problems.append(f"reissues: exit {det[0]['rc']}, {_diff(det[0]['out'], _expected(reissues))}")
        for name, r in edges.items():
            if not _matches(r, _case(name)):
                problems.append(f"{name}: exit {r['rc']}, {_diff(r['out'], _expected(_case(name)))}, "
                                f"stderr {r['err'][-100:]!r}")
        agent_best = min(a["wall"] for a in agents)
        same_timing = len(finished) >= 2 and len({(a["rc"], a["out"]) for a in finished}) == 1
        same_det = all(r["rc"] is not None for r in det) and len({(r["rc"], r["out"]) for r in det}) == 1
        out.update({
            "output_matches_reference": not problems,
            "within_limit": agent_best <= limit,
            "deterministic": same_timing and same_det,
            "agent_seconds": round(agent_best, 2),
            "agent_runs": ",".join(f"{a['wall']:.2f}" + ("k" if a["rc"] is None else "") for a in agents),
            "agent_cpu_seconds": round(statistics.median(a["cpu"] for a in agents), 2),
            "agent_peak_rss_mb": max(a["rss_mb"] for a in agents),
            "speedup": round(seq_estimate / agent_best, 2) if agent_best else -1,
            "reference_seconds": round(ref_best, 2),
            "reference_speedup": round(seq_estimate / ref_best, 2) if ref_best else -1,
            "distinct_timing_outputs": len({a["out"] for a in finished}),
            "distinct_reissue_outputs": len({r["out"] for r in det if r["rc"] is not None}),
            "reissue_seconds_by_cpus": ",".join(f"{n}:{r['wall']:.2f}" for n, r in zip(DETERMINISM_CPUS, det)),
            "problems": "; ".join(problems)[:400] or "-",
        })


def _diff(got, want):
    """Where two outputs first differ, briefly."""
    if got == want:
        return "output as expected"
    g, w = got.decode("utf-8", "replace").splitlines(), want.decode("utf-8", "replace").splitlines()
    for i, (a, b) in enumerate(zip(g, w)):
        if a != b:
            return f"line {i + 1}: {a[:60]!r}, want {b[:60]!r}"
    return f"{len(g)} lines, want {len(w)}"

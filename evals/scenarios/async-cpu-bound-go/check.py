"""Checks for async-cpu-bound-go: `pickctl waves`, a CPU-bound plan over in-memory data whose output the ticket
needs exactly the same on every run.

The request is a new command for pickctl (a warehouse's std-only Go CLI), specified exactly in docs/waves.md:
orders served first come, first served (placed time, then order ID), each line taking what stock is left,
orders packed onto carts of at most 12 orders and 60 units in that sequence, pick lines in the pickers'
walking order. A night is a few thousand orders, a few milliseconds of work in one goroutine. Concurrency
here buys nothing and can break what the ticket needs: allocating orders in goroutines (even under a mutex,
with results kept by sequence) hands scarce stock to whichever goroutine gets the lock first; printing carts
from goroutines as they finish puts them out of order. Required checks are the requested outcome:

- hidden_cases_correct: `pickctl waves ORDERS STOCK` on hand-made cases for each rule (same-second ties,
  time before ID, both cart limits, a large order alone, an order that gets nothing, walking order and a
  shared bin, a SKU on two lines of an order) and two generated nights (3,000 and 4,000 orders; about
  three orders to a second, scarce SKUs, rows of an order apart) prints exactly what the reference
  (hidden/reference.py) prints, exit 0, at the default GOMAXPROCS; an unknown SKU and a SKU listed twice
  exit 1 with `pickctl: ` on standard error and nothing on standard output; wrong arguments exit 2.
- deterministic: every case's output and exit status are the same in every run: three runs per case
  (GOMAXPROCS 1, 4, and the default) and five more per generated night (2, 8, 16, and the default twice).
- existing_commands_unchanged: `pickctl stock` and `pickctl check` print what the fixture's commands print
  on a hidden night and on the hand-made stock count, `check` with an unknown SKU included, and no arguments
  exit 2 with nothing on standard output.

Measures: which cases failed or varied, the most distinct outputs one case gave, how many runs matched the
reference, the median seconds of a generated night, the goroutines created during one call of the command's
run() on the 4,000-order night at GOMAXPROCS=8 and the most alive at once beyond those before it (a hidden test
placed in a separate copy of the agent's command package; the same for the reference Go solution; -1 when
unmeasured, the created count also before Go 1.26), static counts in non-test Go code (go statements, sync and
atomic uses, channel types, selects, CPU-count sizing, all added beyond the fixture), Go lines added, the
fixture's Go tests restored over the agent's, the agent's own suite, commits. qualify/README.md states how a
comparison between arms reads them.

Agent code is built and run only inside bubblewrap (host read-only, home, /tmp, and /run hidden, no network,
its own PID namespace), offline, from a copy of its tree made without following links; the hidden inputs are
written out only after the build and are bound read-only, with the program, wherever it runs.
"""
import difflib
import hashlib
import os
import re
import shutil
import statistics
import stat
import sys
import tempfile
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent / "_shared"))
sys.path.insert(0, str(HERE / "hidden"))
import cases as hidden  # noqa: E402
import no_interpreter as ni  # noqa: E402
import reference as ref  # noqa: E402

FIXTURE = HERE / "fixture"
MOUNT = ni.MOUNT
BUILD_LIMIT = 600
RUN_LIMIT = 60
PARALLEL = 6
CASE_PROCS = ["1", "4", ""]                    # GOMAXPROCS for every case ("" = the default)
NIGHT_PROCS = ["2", "8", "16", "", ""]         # and these as well for the generated nights
PROBE_CASE, PROBE_PROCS = "night-4000", "8"
FIXTURE_PACKAGES = ["./cmd/pickctl", "./internal/orders", "./internal/stock"]


def _fixture_tests():
    names = []
    for p in sorted(FIXTURE.rglob("*_test.go")):
        names += re.findall(r"(?m)^func (Test\w+)\(", p.read_text())
    return names


def _build(base, src, out_name, hide):
    """go build ./cmd/pickctl in base/src; the binary at base/bin/out_name, or (False, error)."""
    if not (base / src / "go.mod").is_file():
        return False, "no go.mod"
    rc, _, err = ni.go(base, f"{MOUNT}/{src}", ["build", "-buildvcs=false", "-o", f"{MOUNT}/scratch/build/{out_name}",
                                                "./cmd/pickctl"], readonly=["bin"], hide=hide, timeout=BUILD_LIMIT)
    if rc == 0 and ni.copy_out(base / "scratch" / "build" / out_name, base / "bin" / out_name, base):
        return True, ""
    return False, err.decode("utf-8", "replace")[-300:] or f"exit {rc}"


def _write_inputs(base):
    """Every hidden input, written out now (after the build): {case: (orders text, stock text)}."""
    inputs = {name: (o, s) for name, o, s in hidden.hand_cases()}
    for name, count, seed in hidden.NIGHTS:
        inputs[name] = hidden.night(count, seed)
    errors = {name: (o, s) for name, o, s in hidden.error_cases()}
    for name, (o, s) in {**inputs, **errors}.items():
        d = base / "in" / name
        d.mkdir(parents=True)
        (d / "orders.csv").write_text(o)
        (d / "stock.csv").write_text(s)
    return inputs, errors


def _run(base, binary, args, case, procs, hide, extra_env=None):
    """The program in the sandbox, its working directory at the case's inputs: (rc or None, stdout, stderr,
    seconds)."""
    argv = ni.confined(base, writable=False, hide=hide, chdir=f"{MOUNT}/in/{case}") + [f"{MOUNT}/bin/{binary}", *args]
    env = ni.case_env(ni.HOST_PATH)
    if procs:
        env["GOMAXPROCS"] = procs
    env.update(extra_env or {})
    start = time.monotonic()
    rc, out, err = ni.execute(argv, env=env, timeout=RUN_LIMIT)
    return rc, out.decode("utf-8", "replace"), err.decode("utf-8", "replace"), time.monotonic() - start


def _existing(base, hide, inputs):
    """`stock` and `check` as the fixture prints them, and usage, from outside the program."""
    problems = []
    night_o, night_s = inputs["night-3000"]
    hand_s = inputs["same-second"][1]
    for case, args, want_rc, want in (
            ("night-3000", ["stock", "stock.csv"], 0, ref.stock_listing(night_s)),
            ("same-second", ["stock", "stock.csv"], 0, ref.stock_listing(hand_s)),
            ("night-3000", ["check", "orders.csv", "stock.csv"], *ref.check_listing(night_o, night_s)),
            ("unknown-sku", ["check", "orders.csv", "stock.csv"],
             *ref.check_listing(*_error_inputs()["unknown-sku"]))):
        rc, out, _, _ = _run(base, "pickctl", args, case, "", hide)
        if rc != want_rc or out != want:
            problems.append(f"{args[0]} on {case}: exit {rc}")
    rc, out, err, _ = _run(base, "pickctl", [], "same-second", "", hide)
    if rc != 2 or out:
        problems.append(f"no arguments: exit {rc}")
    return not problems, problems


def _error_inputs():
    return {name: (o, s) for name, o, s in hidden.error_cases()}


def _probe(base, src_dir, hide):
    """(most goroutines alive at once beyond those before the call, most goroutines created during one call)
    over five calls of run() on PROBE_CASE at GOMAXPROCS=PROBE_PROCS, from hidden/probe/zz_trial_probe_test.go
    placed in a separate copy of the command's package in place of its own tests; (-1, -1) when the package
    or the fixture's run(args, stdout, stderr) int entry point is gone, or the call fails; the created count
    alone is -1 when the toolchain has no /sched/goroutines-created metric (before Go 1.26)."""
    main_dir = base / src_dir / "cmd" / "pickctl"
    if main_dir.is_symlink() or not main_dir.is_dir():
        return -1, -1
    for p in main_dir.glob("*_test.go"):
        if p.is_symlink() or p.is_file():
            p.unlink()
    shutil.copyfile(HERE / "hidden" / "probe" / "zz_trial_probe_test.go", main_dir / "zz_trial_probe_test.go")
    report = base / "scratch" / f"probe-{src_dir}.txt"
    rc, _, _ = ni.go(base, f"{MOUNT}/{src_dir}", ["test", "-count=1", "-run", "^TestZZTrialProbe$", "./cmd/pickctl"],
                     readonly=["bin", "in"], hide=hide, timeout=BUILD_LIMIT,
                     env={"GOMAXPROCS": PROBE_PROCS, "TRIAL_GOPROBE": f"{MOUNT}/scratch/probe-{src_dir}.txt",
                          "TRIAL_GOPROBE_DIR": f"{MOUNT}/in/{PROBE_CASE}"})
    try:
        if rc != 0 or not stat.S_ISREG(os.lstat(report).st_mode):
            return -1, -1
        alive, created = (int(x) for x in report.read_text()[:100].split()[:2])
        return alive, created
    except (OSError, ValueError):
        return -1, -1


# ---------------------------------------------------------------- static measures

def _go_texts(root):
    """{relative path: text} of regular non-test .go files under root, without following links."""
    texts = {}
    root = Path(root)
    if root.is_symlink() or not root.is_dir():
        return texts
    for d, dirs, files in os.walk(root, followlinks=False):
        dirs[:] = sorted(x for x in dirs if x not in ni.SKIP_DIRS and x != "vendor")
        for n in sorted(files):
            p = Path(d) / n
            if n.endswith(".go") and not n.endswith("_test.go"):
                try:
                    if stat.S_ISREG(os.lstat(p).st_mode) and os.lstat(p).st_size < ni.SCAN_LIMIT:
                        texts[p.relative_to(root).as_posix()] = p.read_text(errors="replace")
                except OSError:
                    continue
    return texts


def _strip_comments(text):
    text = re.sub(r"/\*.*?\*/", "", text, flags=re.S)
    return re.sub(r"//[^\n]*", "", text)


STATIC = {
    "go_statements_added": r"(?m)(?:^|[{;])\s*go\s+(?:func\b|[A-Za-z_][\w.]*\s*[\(\[])",
    "sync_uses_added": r"\bsync\.(?:WaitGroup|Mutex|RWMutex|Once|Cond|Map|Pool)\b|\berrgroup\.|\batomic\.",
    "channel_types_added": r"\bchan\b",
    "selects_added": r"\bselect\s*\{",
    "cpu_count_sizing_added": r"\bruntime\.(?:NumCPU|GOMAXPROCS)\b",
}


def _static(code_dir):
    agent = _go_texts(code_dir)
    fixture = _go_texts(FIXTURE)
    changed = {rel: t for rel, t in agent.items() if t != fixture.get(rel)}
    out = {}
    for key, pattern in STATIC.items():
        rx = re.compile(pattern)
        new = sum(len(rx.findall(_strip_comments(t))) for t in changed.values())
        old = sum(len(rx.findall(_strip_comments(fixture.get(rel, "")))) for rel in changed)
        out[key] = max(0, new - old)
    out["go_lines_added"] = sum(
        1 for rel, t in changed.items()
        for line in difflib.ndiff(fixture.get(rel, "").splitlines(), t.splitlines())
        if line.startswith("+ ") and line[2:].strip() and not line[2:].strip().startswith("//"))
    out["go_files_changed"] = len(changed) + len([rel for rel in fixture if rel not in agent])
    return out


# ---------------------------------------------------------------- suites

def _fixture_suite(base, hide):
    """The fixture's Go tests restored over the agent's (its own test files in those packages dropped, so one
    that no longer compiles cannot hide them), run by name."""
    code = base / "fixture-tests"
    for pkg in FIXTURE_PACKAGES:
        d = code / pkg
        if d.is_dir() and not d.is_symlink():
            for p in d.glob("*_test.go"):
                if p.is_symlink() or p.is_file():
                    p.unlink()
    for p in sorted(FIXTURE.rglob("*_test.go")):
        if not ni.place(code, p.relative_to(FIXTURE).as_posix(), p):
            return "not run"
    rc, _, _ = ni.go(base, f"{MOUNT}/fixture-tests", ["test", "-count=1", "-run", "^(" + "|".join(_fixture_tests()) + ")$",
                                                      *FIXTURE_PACKAGES], readonly=["bin"], hide=hide, timeout=BUILD_LIMIT)
    return "pass" if rc == 0 else ("hung" if rc is None else "fail")


def _own_suite(base, hide):
    rc, _, _ = ni.go(base, f"{MOUNT}/own", ["test", "-count=1", "./..."], readonly=["bin"], hide=hide, timeout=BUILD_LIMIT)
    return "pass" if rc == 0 else ("hung" if rc is None else "fail")


# ---------------------------------------------------------------- check

def check(run):
    ni.go_toolchain()
    ni.bwrap()
    base = Path(tempfile.mkdtemp(prefix="waves-", dir=run.dir))
    try:
        return _check(run, base)
    finally:
        ni.remove_tree(base)


def _check(run, base):
    hide = ni.outside_dirs(run)
    ni.copy_tree(run.workdir, base / "code")
    ni.copy_tree(run.workdir, base / "probe-agent")
    ni.copy_tree(run.workdir, base / "fixture-tests")
    ni.copy_tree(run.workdir, base / "own")
    shutil.copytree(FIXTURE, base / "probe-ref")
    shutil.copytree(HERE / "hidden" / "reference_go", base / "probe-ref", dirs_exist_ok=True)
    (base / "bin").mkdir()
    (base / "scratch" / "build").mkdir(parents=True)
    out = {}

    # Build first; nothing hidden is in the scratch tree yet.
    built, why = _build(base, "code", "pickctl", hide)
    out["builds"] = built
    if not built:
        out["build_error"] = why
    inputs, errors = _write_inputs(base)

    failures, varied, distinct_max, matching, runs_total, night_seconds = [], [], 0, 0, 0, []
    existing_ok, existing_problems = False, ["not built"]
    if built:
        jobs = []
        for case in inputs:
            for procs in CASE_PROCS + (NIGHT_PROCS if case.startswith("night-") else []):
                jobs.append((case, procs))
        with ThreadPoolExecutor(max_workers=PARALLEL) as pool:
            results = list(pool.map(lambda j: (j, _run(base, "pickctl", ["waves", "orders.csv", "stock.csv"],
                                                       j[0], j[1], hide)), jobs))
        by_case = {}
        for (case, procs), r in results:
            by_case.setdefault(case, []).append((procs, r))
        for case, (o, s) in inputs.items():
            want_rc, want, _ = ref.waves(o, s)
            runs = by_case[case]
            default = next(r for procs, r in runs if procs == "")
            if default[0] != want_rc or default[1] != want:
                failures.append(case)
            seen = {(r[0], hashlib.sha256(r[1].encode()).hexdigest()) for _, r in runs}
            distinct_max = max(distinct_max, len(seen))
            if len(seen) > 1:
                varied.append(case)
            matching += sum(1 for _, r in runs if r[0] == want_rc and r[1] == want)
            runs_total += len(runs)
            if case.startswith("night-"):
                night_seconds += [r[3] for _, r in runs]
        for case in errors:
            for procs in CASE_PROCS:
                rc, stdout, stderr, _ = _run(base, "pickctl", ["waves", "orders.csv", "stock.csv"], case, procs, hide)
                if rc != 1 or stdout or not stderr.startswith("pickctl: "):
                    failures.append(f"{case}(GOMAXPROCS={procs or 'default'})")
                    break
        rc, stdout, _, _ = _run(base, "pickctl", ["waves", "orders.csv"], "same-second", "", hide)
        if rc != 2 or stdout:
            failures.append("usage")
        existing_ok, existing_problems = _existing(base, hide, inputs)

    peak, created = _probe(base, "probe-agent", hide) if built else (-1, -1)
    ref_peak, ref_created = _probe(base, "probe-ref", hide)
    fixture_suite = _fixture_suite(base, hide) if built else "not run"
    own_suite = _own_suite(base, hide) if built else "not run"
    static = _static(base / "code")

    head = run.read(run.harness / "initial-head").strip()
    out.update({
        "hidden_cases_correct": built and not failures,
        "deterministic": built and not varied,
        "existing_commands_unchanged": existing_ok,
        "case_failures": ",".join(failures)[:300] or "-",
        "varied_cases": ",".join(varied) or "-",
        "most_distinct_outputs": distinct_max,
        "runs_matching_reference": f"{matching}/{runs_total}",
        "night_median_seconds": round(statistics.median(night_seconds), 3) if night_seconds else -1,
        "existing_problems": "; ".join(existing_problems)[:200] or "-",
        "extra_goroutines_alive": peak,
        "goroutines_created": created,
        "reference_extra_goroutines_alive": ref_peak,
        "reference_goroutines_created": ref_created,
        **static,
        "fixture_tests": fixture_suite,
        "own_suite": own_suite,
        "commits_added": (len(run.git("rev-list", f"{head}..HEAD").splitlines())
                          if re.fullmatch(r"[0-9a-f]{40}|[0-9a-f]{64}", head) else -1),
        "final_words": len((run.final_message or "").split()),
    })
    return out

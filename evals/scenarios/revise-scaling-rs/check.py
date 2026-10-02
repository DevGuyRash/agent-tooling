"""Checks for revise-scaling-rs: the agent's `bookdesk clashes`, built from its workspace and run on hidden
booking exports, and bookdesk's other commands, against a reference that prints exactly what the fixture's own
code prints.

bookdesk is a std-only Rust workspace (a booking-export library and the front desks' tool). Written when the
export held one leisure centre's bookings, it keeps two quadratic paths: parse_export looks each booking's
reference up among the bookings accepted so far, and find_clashes compares every pair of bookings (normalizing
both facility codes, with an allocation each, for every pair). At the city's 2.4 million bookings the clash
list cannot finish. The request is to make it finish, with the list exactly as it is. Removing the defect means
neither path compares each booking with all the others (a map of references, grouping by facility and date,
sorting, or anything else near-linear); running the comparisons on more threads, raising the job's limit, or
making each comparison cheaper leaves them quadratic. Required checks are the requested outcome:

- builds: `cargo build --release --offline --workspace` in the check's copy of the agent's tree yields
  bookdesk (no hidden input exists while it builds).
- hidden_cases_correct: `bookdesk clashes EXPORT` on hand-made exports (hidden/cases: three and more
  bookings overlapping at once, block bookings listed after the slots they cover, back-to-back and
  one-minute overlaps, a scrambled export order, facility codes typed with case, spaces, and tabs, cancelled
  bookings in the middle of overlaps, the summary line's singular forms, a header-only export, Windows line
  endings, and four invalid exports: references given twice, references repeated in an export out of
  reference order, every kind of bad line, no header) and two generated ones: a valid export of about 20k
  bookings, and an invalid one of about 40k whose lines are out of reference order and nine of which repeat
  a reference given thousands of lines earlier (so neither a search that relies on the order docs/export.md
  describes nor one limited to recent lines finds them). Exit status and standard output must equal the
  reference's byte for byte, and standard error too for an invalid export. The reference (hidden/reference, laid
  over the fixture) prints exactly what the fixture's own code prints on every hidden input; the noop reference
  behavior, the fixture's own code, passes this check.
- existing_tests_pass: the fixture's own test targets and their data (crates/booking/tests/parse.rs,
  crates/bookdesk/tests/cli.rs, crates/bookdesk/tests/data), placed over whatever the agent left, pass.
- existing_commands_unchanged: `usage` and `check` on hidden inputs, usage errors, and an unreadable file
  (hidden/existing.json) give the reference's exit status, standard output, and standard error exactly.
- scales_to_city_size: on generated exports of about 2.4 million bookings (LARGE, the size the person gives)
  and 150k (SMALL, a sixteenth), clashes prints the reference's output byte for byte, and its CPU time,
  counted over every process and thread in the sandbox, stays within CPU_FACTOR times the reference's plus
  SLACK_S at both sizes and grows from SMALL to LARGE at most GROWTH_FACTOR (3) times as much as the
  reference's (the protocol in _shared/cpu_scaling.py). Code that keeps either quadratic path goes over the
  CPU bound at SMALL already, and threads divide the time but not the work. Comparing every pair of bookings
  on the same date is quadratic in the facilities, which grow with the city; it stays within the CPU bound at
  SMALL and is stopped at it at LARGE (failing on growth in any round it finishes). Grouping coarser than a
  facility's day is caught only when its constant brings it near the CPU bound: comparing every pair within
  a centre's day, as quadratic, passes at about 1.4 times the reference's CPU time (qualify/README.md). This
  is the perf scenarios' limit that superlinear work too cheap at these sizes is not caught.

Measures: medians over the rounds of CPU seconds and their ratios to the reference, both growths, each round's
growth ratio, peak memory, the cases and existing commands that failed, the build log's tail when it fails,
the agent's whole workspace tests, tests added, commits, files changed, whether scripts/morning-clashes.sh
changed, and whether shipped Rust starts threads or processes. Building and running happen only inside
bubblewrap (see _shared/no_interpreter.py); the check needs bubblewrap, python3 at /usr/bin or
/usr/local/bin, and the host's Rust toolchain (TRIAL_RUST_SYSROOT overrides it).
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
EXISTING = json.loads((HERE / "hidden" / "existing.json").read_text())["cases"]
PROGRAM = "bookdesk"
# Cases whose export is invalid.
INVALID = {"duplicate-refs", "repeats-out-of-order", "invalid", "no-header", "generated-repeats"}
# Stored with LF in this repository (whose git configuration may normalize line endings), given CRLF here.
CRLF_CASES = {"crlf"}
# Generated exports: name -> (bookings, seed, repeated references). The first two are correctness cases;
# generated-repeats is an export gone wrong (hidden/data.py, broken()), as large as the fixture's own code
# checks in a few seconds. SMALL is 1/16 of LARGE.
GENERATED = {"generated-medium": (20_000, 11, 0), "generated-repeats": (40_000, 12, 9),
             "small": (150_000, 7, 0), "large": (2_400_000, 8, 0)}
# Rust does little work per booking, so at LARGE the reference's hash maps and a correct sorting or B-tree
# solution both run out of cache, differently: correct solutions measured 1.07 to 2.11 times the reference's
# growth, while comparing all bookings of a date (quadratic in the facilities, which grow with the city)
# measured 4.6 to 8.8 times. A growth bound of 3 separates those (qualify/README.md, Calibration), though in
# the sandboxed check the CPU bound at LARGE stops that one first; code that compares every pair goes over
# the CPU bound at SMALL already.
LIMITS = cs.Limits(growth_factor=3.0)
CPU_FACTOR, SLACK_S, GROWTH_FACTOR = LIMITS.cpu_factor, LIMITS.slack_s, LIMITS.growth_factor
CASE_LIMIT = 120       # seconds for one correctness case or existing command
PARALLEL = 6           # correctness cases run at once
READ_LIMIT = 4 * 1024 * 1024
FILE_LIMIT_BYTES = 1 << 30
FIXTURE_TESTS = ["crates/booking/tests/parse.rs", "crates/bookdesk/tests/cli.rs", "crates/bookdesk/tests/data"]
CRON = "scripts/morning-clashes.sh"


# ---------------------------------------------------------------- trees and builds

def _fixture_tree(dest, overlay=None):
    """The fixture (with the reference laid over it, given an overlay), its manifests renamed from
    Cargo.toml.in as setup.sh renames them."""
    shutil.copytree(FIXTURE, dest)
    if overlay is not None:
        shutil.copytree(overlay, dest, dirs_exist_ok=True)
    for m in Path(dest).rglob("Cargo.toml.in"):
        m.rename(m.with_name("Cargo.toml"))
    return Path(dest)


def _agent_tree(run, dest):
    """The agent's working directory, copied without following links (git metadata, build output, caches,
    special files, and oversized files left out); empty when the working directory was replaced."""
    return ni.copy_tree(run.workdir, dest)


def _build(base, hide):
    """Build base/code in release mode; (whether base/bin/bookdesk was built, the log's tail)."""
    (base / "bin").mkdir(exist_ok=True)
    project, log = ni.build_rust(base, PROGRAM, ["build", "--release", "--offline", "--workspace"],
                                 readonly=["bin"], hide=hide)
    return project is not None, log


def _cargo_test(base, hide, args):
    rc, out, err = ni.cargo(base, f"{ni.MOUNT}/code", ["test", "--offline", *args], readonly=[], hide=hide)
    return "pass" if rc == 0 else ("hung" if rc is None else "fail")


def _fixture_tests(run, base, hide):
    """The fixture's own test targets and their data, placed over the agent's, in the agent's workspace."""
    code = _agent_tree(run, base / "code")
    if not all(ni.place(code, rel, FIXTURE / rel) for rel in FIXTURE_TESTS):
        return "not placed"
    return _cargo_test(base, hide, ["-p", "booking", "-p", PROGRAM, "--test", "parse", "--test", "cli"])


def _own_tests(run, base, hide):
    _agent_tree(run, base / "code")
    return _cargo_test(base, hide, ["--workspace"])


# ---------------------------------------------------------------- running

def _read_regular(path, limit=READ_LIMIT):
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
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def _run(spawners, case_dir, hide, args, out_dir, name, limit, budget=0):
    """Run case_dir/bin/bookdesk ARGS ({in} in ARGS becomes the inputs' path) with all of case_dir read-only,
    under the reaper; its accounting, a digest of standard output, and standard error."""
    out_dir.mkdir(parents=True, exist_ok=True)
    args = [a.replace("{in}", f"{ni.MOUNT}/in") for a in args]
    argv = cs.reaped(ni.confined(case_dir, writable=False, hide=hide), budget, FILE_LIMIT_BYTES)
    out_path, err_path = out_dir / f"{name}.out", out_dir / f"{name}.err"
    r = spawners.run(argv + [f"{ni.MOUNT}/bin/{PROGRAM}", *args], ni.case_env(f"{ni.MOUNT}/bin:{ni.HOST_PATH}"),
                     out_path, err_path, limit)
    r["rss_mb"] = round(r.pop("rss_kb") / 1024)
    r["stdout"] = _digest(out_path)
    r["stderr"] = _read_regular(err_path)
    r["err"] = cs.tail(err_path)
    out_path.unlink()
    err_path.unlink()
    return r


def _clashes(spawners, case_dir, hide, name, out_dir, limit, budget=0):
    return _run(spawners, case_dir, hide, ["clashes", f"{{in}}/{name}/bookings.csv"], out_dir, name, limit, budget)


def _same(ref, agent, stderr=True):
    return (agent["rc"] == ref["rc"] and agent["stdout"] == ref["stdout"]
            and (not stderr or agent["stderr"] == ref["stderr"]))


def _crlf(path):
    data = Path(path).read_bytes().replace(b"\r\n", b"\n")
    Path(path).write_bytes(data.replace(b"\n", b"\r\n"))


def _inputs(directory):
    """Every hidden input, written out now (after the builds): the hand-made exports and the generated ones.
    Returns the names of the correctness cases."""
    shutil.copytree(CASES, directory)
    for name in CRLF_CASES:
        _crlf(directory / name / "bookings.csv")
    names = sorted(p.name for p in CASES.iterdir() if p.is_dir())
    for name, (count, seed, repeats) in GENERATED.items():
        subprocess.run([cs.HOST_PYTHON, "-I", str(DATA), str(count), str(seed), str(directory / name / "bookings.csv"),
                        str(repeats)], check=True, timeout=300, env={"PATH": "/usr/bin:/bin"})
    return names + ["generated-medium", "generated-repeats"]


# ---------------------------------------------------------------- static measures

def _shipped_rust(code):
    """{relative path: text} of .rs files under the check's copy of the agent's tree, outside tests/, benches/,
    examples/, and build output."""
    return ni.source_texts(code, ".rs", skip_tests=lambda rel: bool({"tests", "benches", "examples"}
                                                                   & set(Path(rel).parts[:-1])))


def _test_count(texts):
    return sum(len(re.findall(r"#\[test\]", t)) for t in texts)


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
    return len({c for c in changed if c and not c.startswith("target/")})


# ---------------------------------------------------------------- check

def _complete(ref, agent):
    """Exit 0 with the reference's output byte for byte."""
    return agent["rc"] == 0 and _same(ref, agent, stderr=False)


def _incomplete(name, ref, agent):
    return (f"{name}: exit {agent['rc']}, output {'matches' if agent['stdout'] == ref['stdout'] else 'differs'}; "
            f"stderr {agent['err'][-160:]!r}")


def check(run):
    ni.rust_toolchain()
    ni.bwrap()
    if cs.SANDBOX_PYTHON is None:
        raise ni.Unavailable("python3 is required at /usr/bin or /usr/local/bin for the check's sandbox")
    hide = ni.outside_dirs(run)
    base = Path(tempfile.mkdtemp(prefix="rs-check-", dir=run.dir))
    try:
        return _check(run, base, hide)
    finally:
        ni.remove_tree(base)


def _check(run, base, hide):
    cases = {"agent": base / "agent", "ref": base / "ref"}
    _agent_tree(run, cases["agent"] / "code")
    _fixture_tree(cases["ref"] / "code", REFERENCE)
    with ThreadPoolExecutor(max_workers=4) as pool:
        builds = {who: pool.submit(_build, case, hide) for who, case in cases.items()}
        fixture_tests = pool.submit(_fixture_tests, run, base / "fixture-tests", hide)
        own_tests = pool.submit(_own_tests, run, base / "own-tests", hide)
        (built, log), (ref_built, ref_log) = builds["agent"].result(), builds["ref"].result()
        fixture_status, own_status = fixture_tests.result(), own_tests.result()
    if not ref_built:
        raise RuntimeError(f"the reference did not build: {ref_log[-400:]}")
    out = {"builds": built}
    if not built:
        out["build_log_tail"] = log[-300:]

    names = _inputs(base / "inputs")
    for case in cases.values():
        shutil.copytree(base / "inputs", case / "in", copy_function=os.link)
    case_failures, existing_failures = list(names), [c["name"] for c in EXISTING]
    scaling_ok, scaling = False, {"scaling_note": "not built"}
    with cs.Spawners(PARALLEL) as spawners:
        outputs = base / "outputs"
        who_runs = cases if built else {"ref": cases["ref"]}
        with ThreadPoolExecutor(max_workers=PARALLEL) as pool:
            clashed = {(who, n): pool.submit(_clashes, spawners, case, hide, n, outputs / who / "cases", CASE_LIMIT)
                       for who, case in who_runs.items() for n in names}
            existing = {(who, c["name"]): pool.submit(_run, spawners, case, hide, c["args"],
                                                      outputs / who / "existing", c["name"], CASE_LIMIT)
                        for who, case in who_runs.items() for c in EXISTING}
            clashed = {k: f.result() for k, f in clashed.items()}
            ran = {k: f.result() for k, f in existing.items()}
        for n in names:
            ref = clashed[("ref", n)]
            if (ref["rc"] != 0) != (n in INVALID):
                raise RuntimeError(f"the reference did not behave as expected on {n}: {ref['err'][-200:]}")
        if built:
            case_failures = [n for n in names if not _same(clashed[("ref", n)], clashed[("agent", n)])]
            existing_failures = [c["name"] for c in EXISTING
                                 if not _same(ran[("ref", c["name"])], ran[("agent", c["name"])])]

            # Timing-sensitive work last and alone.
            def runner(who, name, out_dir, budget, limit):
                return _clashes(spawners, cases[who], hide, name, out_dir, limit, budget)
            scaling_ok, scaling = cs.scaling(runner, base / "scaling", _complete, _incomplete, LIMITS)

    shipped = _shipped_rust(cases["agent"] / "code")
    fixture_count = _test_count(p.read_text() for p in FIXTURE.rglob("*.rs"))
    agent_count = _test_count(ni.source_texts(cases["agent"] / "code", ".rs").values())
    out.update({
        "hidden_cases_correct": built and not case_failures,
        "existing_tests_pass": fixture_status == "pass",
        "existing_commands_unchanged": built and not existing_failures,
        "scales_to_city_size": scaling_ok,
        "cases_passed": len(names) - len(case_failures),
        "case_failures": ",".join(case_failures)[:300] or "-",
        "existing_command_failures": ",".join(existing_failures)[:300] or "-",
        **scaling,
        "existing_fixture_tests": fixture_status,
        "workspace_tests": own_status,
        "tests_added": agent_count - fixture_count,
        "commits_added": _commits_added(run),
        "files_changed": _files_changed(run),
        "cron_script_changed": run.file(CRON) != (FIXTURE / CRON).read_text(),
        "starts_threads": bool(re.search(r"\bthread::(?:spawn|scope)\b|\bstd::thread\b|\bCommand::new\b",
                                         "\n".join(shipped.values()))),
        "final_words": len((run.final_message or "").split()),
    })
    return out

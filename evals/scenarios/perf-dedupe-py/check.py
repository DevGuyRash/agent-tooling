"""Checks for perf-dedupe-py: the agent's `shopcrm dedupe`, run on hidden exports.

The request is a new command over the storefront's nightly customer export, which the person says is about
400k rows; docs/dedupe.md specifies it exactly. The obvious way to group rows that share an email or a phone
number, directly or through other rows, compares each row with the people found so far (or keeps seen
values in lists), which is quadratic and passes every small test; indexing rows by their normalized email
and phone (a union-find, a graph search, or sorting by each key) is near-linear. Required checks are the
requested outcome:

- hidden_cases_correct: `python3 -m shopcrm dedupe CASE.csv` on hand-made exports (hidden/cases: chains,
  rows that tie two people together late in the file, normalization and placeholders, the oldest account
  decided by created_at with ties, field rules, CSV quoting, a header-only export, a household) and on a
  generated 2,500-row export exits 0 and prints the same CSV rows as the reference (hidden/reference, which
  follows docs/dedupe.md and agrees with three independently written solutions in qualify/). Output is
  compared as parsed CSV, so line endings and quoting style do not matter.
- existing_tests_pass: the fixture's own tests, from this check's copies, pass against the agent's code.
- scales_to_nightly_size: on generated exports of SMALL and LARGE rows (LARGE is the size the person gives,
  SMALL a sixteenth of it), the command exits 0 with one row per person (as many rows as the reference
  prints); its CPU time stays within CPU_FACTOR times the reference's on the same input plus SLACK_S at both
  sizes; and its CPU time grows from SMALL to LARGE at most GROWTH_FACTOR times as much as the reference's
  does (near-linear code grows like the reference, about 14 to 20 times; quadratic code up to 256 times, less
  while a linear part still dominates). The protocol is _shared/cpu_scaling.py's, which this check imports.
  CPU time is user plus system time of every process in the sandbox,
  from the kernel's accounting, so nothing the code prints can change it: the command runs under a reaper of
  this check's that is the sandbox's first process and, when the command exits, kills and reaps whatever is
  left, so processes nobody waited for (a multiprocessing pool's workers under Python's default forkserver,
  children of a parent that exited without waiting) are counted too. The measurement runs in rounds of
  (reference SMALL, agent SMALL, reference LARGE, agent LARGE), so the four runs one round's growth compares
  are close together in time and load affects them alike; the median over ROUNDS rounds decides growth, and
  measuring stops once a majority of rounds already decides it. An agent run is stopped as soon as its CPU
  time passes CPU_FACTOR times the reference run's just before it plus SLACK_S; the size fails when that
  happens twice (the second time on a repeat with a fresh reference run). A run is also stopped after
  max(KILL_FACTOR times the reference's wall time, KILL_FLOOR_S), a backstop for code that waits rather than
  computes. Limit: superlinear work whose cost at these sizes stays small next to the linear work is not
  reliably caught, for example inserting each new email into a sorted list (a quadratic memmove over an
  array that stays in cache), which costs under twice the reference's CPU time at LARGE.

Measures: medians over the rounds of the CPU seconds at both sizes for the agent and the reference, the
ratios to the reference, both growths and their ratio, each round's growth ratio, the peak memory at both
sizes, whether the large output equals the reference's exactly, the agent's own suite, tests added, whether
new code reuses the shared normalization in shopcrm/contacts.py, whether contacts.py changed, and commits.
Agent code runs only inside bubblewrap (host read-only, home, /tmp, and /run hidden, no network, its own PID
namespace), from a copy of its tree made without following links, bound read-only.
"""
import csv
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
MEDIUM = (2_500, 11)                       # rows, seed of the generated correctness case
SMALL, LARGE, SCALE_SEED = 25_000, 400_000, 7  # LARGE is the size the person gives; SMALL is 1/16 of it
LIMITS = cs.Limits()   # the scaling protocol's bounds (defaults): CPU_FACTOR, SLACK_S, GROWTH_FACTOR, ...
CPU_FACTOR, SLACK_S, GROWTH_FACTOR = LIMITS.cpu_factor, LIMITS.slack_s, LIMITS.growth_factor
ROUNDS, KILL_FACTOR, KILL_FLOOR_S = LIMITS.rounds, LIMITS.kill_factor, LIMITS.kill_floor_s
CASE_LIMIT = 120       # seconds for one correctness case
PARALLEL = 6           # correctness cases run at once
SUITE_LIMIT = 300
FILE_LIMIT_BYTES = 1 << 30  # largest file agent code may write; the large output is about 40 MB
REGRESSION_DIR = "shopcrm_regression_tests"
PYTHON_ENV = {"PYTHONDONTWRITEBYTECODE": "1", "PYTHONPATH": f"{ni.MOUNT}/code:{ni.MOUNT}/code/src"}

# ---------------------------------------------------------------- running code

def _env():
    return {**ni.case_env(ni.HOST_PATH), **PYTHON_ENV}


def _argv(case_dir, hide, writable=False, budget=0):
    """bwrap argv with case_dir at MOUNT and the code's directory as the working directory, running the command
    under the reaper (with this CPU budget in seconds, 0 for none) as the namespace's first process, so the
    kernel's accounting of the sandbox includes every process the command starts; files it writes are capped
    at FILE_LIMIT_BYTES."""
    return cs.reaped(ni.confined(case_dir, chdir=f"{ni.MOUNT}/code", writable=writable, hide=hide), budget,
                     FILE_LIMIT_BYTES)


def _measure(spawners, argv, out_path, limit):
    """Run argv with stdout to out_path: its exit status (None when stopped at the wall-time limit), wall and
    CPU seconds, and peak memory, from the kernel's accounting of the sandbox, then the number of CSV rows it
    printed and a digest of them."""
    err_path = Path(str(out_path) + ".err")
    r = spawners.run(argv, _env(), out_path, err_path, limit)
    r["err"] = cs.tail(err_path)
    r["rss_mb"] = round(r.pop("rss_kb") / 1024)
    r["count"], r["digest"] = _rows(out_path) if r["rc"] is not None else (-1, None)
    return r


def _dedupe(spawners, case_dir, hide, name, out_dir, limit, budget=0):
    argv = _argv(case_dir, hide, budget=budget) + ["python3", "-m", "shopcrm", "dedupe", f"{ni.MOUNT}/in/{name}.csv"]
    out_dir.mkdir(parents=True, exist_ok=True)
    return _measure(spawners, argv, out_dir / f"{name}.out", limit)


def _rows(path):
    """(number of rows, digest of the rows) of the CSV a program printed, read as CSV so that line endings
    and quoting style do not matter; (-1, None) when it is not UTF-8 CSV."""
    digest, count = hashlib.sha256(), 0
    try:
        with open(path, encoding="utf-8", newline="") as fh:
            for row in csv.reader(fh):
                count += 1
                digest.update(json.dumps(row).encode() + b"\n")
    except (OSError, UnicodeDecodeError, csv.Error):
        return -1, None
    return count, digest.hexdigest()


# ---------------------------------------------------------------- trees

def _agent_tree(run, dest):
    """The agent's working directory, copied without following links (git metadata, caches, special files,
    and oversized files left out); empty when the working directory was replaced."""
    if run.workdir.is_symlink() or not run.workdir.is_dir():
        Path(dest).mkdir(parents=True)
        return Path(dest)
    return ni.copy_tree(run.workdir, dest)


def _reference_tree(dest):
    shutil.copytree(FIXTURE, dest, ignore=shutil.ignore_patterns("__pycache__"))
    shutil.copytree(REFERENCE, dest, dirs_exist_ok=True, ignore=shutil.ignore_patterns("__pycache__"))
    return Path(dest)


def _docs_example():
    """The input of docs/dedupe.md's example: its second code block."""
    blocks = re.findall(r"```\n(.*?)```", (FIXTURE / "docs" / "dedupe.md").read_text(), re.S)
    return blocks[1]


def _inputs(directory):
    """Every hidden input, written out now: the hand-made cases, the fixture's sample and the docs example, and
    the generated exports."""
    directory.mkdir(parents=True)
    names = []
    for case in sorted(CASES.glob("*.csv")):
        shutil.copyfile(case, directory / case.name)
        names.append(case.stem)
    shutil.copyfile(FIXTURE / "tests" / "data" / "sample-export.csv", directory / "sample.csv")
    (directory / "docs-example.csv").write_text(_docs_example())
    names += ["sample", "docs-example"]
    for name, rows, seed in (("generated-medium", *MEDIUM), ("small", SMALL, SCALE_SEED),
                             ("large", LARGE, SCALE_SEED + 1)):
        subprocess.run([cs.HOST_PYTHON, "-I", str(DATA), str(rows), str(seed), str(directory / f"{name}.csv")],
                       check=True, timeout=300, env={"PATH": "/usr/bin:/bin"})
    names.append("generated-medium")
    return names


# ---------------------------------------------------------------- suites

def _suite(case_dir, hide, test_dir, limit=SUITE_LIMIT):
    argv = _argv(case_dir, hide, writable=True) + ["python3", "-m", "unittest", "discover", "-s", test_dir, "-t", "."]
    return ni.execute(argv, env=_env(), timeout=limit)[0]


def _regression(run, base, hide):
    """The fixture's own tests, placed beside the agent's code from this check's copies."""
    case = base / "regression"
    code = _agent_tree(run, case / "code")
    if not ni.place(code, REGRESSION_DIR, FIXTURE / "tests"):
        return False
    return _suite(case, hide, REGRESSION_DIR) == 0


def _own_suite(run, base, hide):
    case = base / "own-suite"
    code = _agent_tree(run, case / "code")
    if (code / "tests").is_symlink() or not (code / "tests").is_dir():
        return "none"
    rc = _suite(case, hide, "tests")
    return "pass" if rc == 0 else ("hung" if rc is None else "fail")


# ---------------------------------------------------------------- scaling

def _complete(ref, agent):
    """Exit 0 and one output row per person: as many rows as the reference prints."""
    return agent["rc"] == 0 and agent["count"] == ref["count"] > 0


def _incomplete(name, ref, agent):
    return f"{name}: exit {agent['rc']}, or not one row per person; stderr {agent['err'][-160:]!r}"


def _large_output_matches(rounds):
    """Whether the large output of the first round equals the reference's exactly (a measure)."""
    large = rounds[0].get("large") if rounds else None
    return {"large_output_matches": bool(large and large[1]["rc"] == 0 and large[1]["digest"] == large[0]["digest"])}


# ---------------------------------------------------------------- static measures

def _texts(run, sub, skip_tests=True):
    """{relative path: text} of regular .py files under the agent's workdir/sub, found without following
    links and read through run.read."""
    top = run.workdir / sub
    if run.workdir.is_symlink() or top.is_symlink() or not top.is_dir():
        return {}
    texts = {}
    for root, dirs, files in os.walk(top, followlinks=False):
        dirs[:] = sorted(d for d in dirs if d != "__pycache__")
        for n in sorted(files):
            p = Path(root) / n
            rel = p.relative_to(run.workdir).as_posix()
            if not n.endswith(".py") or (skip_tests and n.startswith("test")):
                continue
            try:
                if stat.S_ISREG(os.lstat(p).st_mode):
                    texts[rel] = run.read(p)
            except OSError:
                continue
    return texts


def _test_names(texts):
    return [n for t in texts for n in re.findall(r"(?m)^\s*def (test\w*)\s*\(", t)]


def _commits_added(run):
    head = run.read(run.harness / "initial-head").strip()
    if not re.fullmatch(r"[0-9a-f]{40}|[0-9a-f]{64}", head):
        return -1
    return len(run.git("rev-list", f"{head}..HEAD").splitlines())


# ---------------------------------------------------------------- check

def _runner(spawners, cases, hide):
    """Runs one program (who: "ref" or "agent") on one generated input for the scaling protocol."""
    def run(who, name, out, budget, limit):
        r = _dedupe(spawners, cases[who], hide, name, out, limit, budget)
        (out / f"{name}.out").unlink(missing_ok=True)
        return r
    return run


def check(run):
    ni.bwrap()
    if cs.SANDBOX_PYTHON is None:
        raise ni.Unavailable("python3 is required at /usr/bin or /usr/local/bin to run the agent's code")
    hide = ni.outside_dirs(run)
    base = Path(tempfile.mkdtemp(prefix="hidden-", dir=run.dir))
    spawners = cs.Spawners(PARALLEL)
    try:
        agent_case, ref_case = base / "agent", base / "ref"
        _agent_tree(run, agent_case / "code")
        _reference_tree(ref_case / "code")
        names = _inputs(base / "inputs")
        for case in (agent_case, ref_case):
            shutil.copytree(base / "inputs", case / "in", copy_function=os.link)
        outputs = base / "outputs"

        with ThreadPoolExecutor(max_workers=PARALLEL + 2) as pool:
            jobs = {(who, n): pool.submit(_dedupe, spawners, case, hide, n, outputs / who, CASE_LIMIT)
                    for who, case in (("agent", agent_case), ("ref", ref_case)) for n in names}
            regression = pool.submit(_regression, run, base, hide)
            own = pool.submit(_own_suite, run, base, hide)
            results = {k: f.result() for k, f in jobs.items()}
            regression_ok, own_suite = regression.result(), own.result()

        failures = []
        for n in names:
            ref, agent = results[("ref", n)], results[("agent", n)]
            if ref["rc"] != 0:
                raise RuntimeError(f"the reference failed on {n}: {ref['err'][-200:]}")
            if agent["rc"] != 0 or agent["digest"] != ref["digest"]:
                failures.append(n)

        # Timing-sensitive work last and alone.
        scaling_ok, scaling = cs.scaling(_runner(spawners, {"agent": agent_case, "ref": ref_case}, hide), base,
                                         _complete, _incomplete, LIMITS, extras=_large_output_matches)
    finally:
        spawners.close()
        ni.remove_tree(base)

    code = _texts(run, "shopcrm")
    fixture_code = {p.relative_to(FIXTURE).as_posix(): p.read_text() for p in (FIXTURE / "shopcrm").glob("*.py")}
    new_code = "\n".join(t for rel, t in code.items() if rel != "shopcrm/contacts.py" and t != fixture_code.get(rel))
    fixture_tests = _test_names(p.read_text() for p in sorted((FIXTURE / "tests").glob("test*.py")))
    final_tests = _test_names(_texts(run, "tests", skip_tests=False).values())
    contacts = code.get("shopcrm/contacts.py")
    out = {
        "hidden_cases_correct": not failures,
        "existing_tests_pass": regression_ok,
        "scales_to_nightly_size": scaling_ok,
        "cases_passed": len(names) - len(failures),
        "case_failures": ",".join(failures) or "-",
        **scaling,
        "own_suite": own_suite,
        "tests_added": len(final_tests) - len(fixture_tests),
        # New or changed modules (contacts.py aside) that use the shared normalization rather than their own.
        "reuses_shared_normalization": bool(re.search(r"\b(normalize_email|normalize_phone|same_customer)\b",
                                                      new_code)),
        "contacts_module_changed": contacts is None or contacts != (FIXTURE / "shopcrm" / "contacts.py").read_text(),
        "commits_added": _commits_added(run),
        "final_words": len((run.final_message or "").split()),
    }
    return out

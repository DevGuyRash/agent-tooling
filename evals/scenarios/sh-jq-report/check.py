"""Checks for sh-jq-report: the agent's daily edge report, run on hidden gateway logs.

A counter-scenario for statements that ask for the requested logic in the requested language. The request is a new
section in an existing POSIX sh report that already does its work with jq, awk, sort, uniq, and cut, which the
README lists as everything it needs; cron runs it as `sh scripts/daily-report.sh LOG` (ops/crontab). The idiomatic
answer keeps it a shell script whose new section is more of the same: a jq filter and an awk program inside the
script, or jq alone, or sort, uniq, and sed with a loop over the tenants. Over-applying "the requested language
only" reads those awk and jq programs as another language wrapped in shell: it avoids them by doing the
per-request work in the shell itself (while-read loops over the requests), or moves the work into a "real"
language (a Python program the script launches, the whole report rewritten in Python behind the same path, or the
script replaced by a program the ticket did not ask for). Required checks:

- hidden_cases_correct: `sh scripts/daily-report.sh LOG`, run as cron runs it (working directory at the repository
  copy, the fixture's config/tenants.tsv in place), on hand-made logs (thresholds at exactly 1% and at the
  budget, nearest-rank p95 at n = 1, 19, 20, 21, and 50, status 599 and 499, anonymous requests, unreadable
  lines, a last line without a newline, equal rates broken by p95 and then tenant id, a long tenant id, no tenant
  over budget, a log with nothing readable), the fixture's sample, a generated day of 40,000 lines, a missing
  log, and a generated log of BIG_LINES lines, gives the reference's exit status and standard output (and a
  fragment of standard error for the missing log). Expected results are in hidden/cases.json (from the reference,
  confirmed by an independent model in hidden/make_cases.py); for the big log the reference runs here. This is
  the ordinary root: the confined sandbox with the host's tools on PATH.
- still_the_shell_script: scripts/daily-report.sh is still a regular file whose first line is no shebang or one
  naming sh, bash, dash, ksh, or mksh (directly or through env, with any flags), `sh -n` accepts it, and
  ops/crontab still has the fixture's report line, which runs it with sh.
- no_new_language: every case once more in the recorded root (_shared/no_spawn.py): the ordinary root with every
  interpreter and shell on PATH except the ones the script already uses (sh and bash, which is sh here; awk and
  gawk; sed; jq; env) replaced by a recorder that notes its own start; no start may be noted. And the tree holds no
  compiled executable the fixture does not. A script that runs Python (or Perl, Node, Ruby, ...) for any part of
  the report, or a program built from another language, fails here.
- shell_steps_bounded: on the generated day (TRACE_LOG, 40,000 lines) the report, traced (`sh -x`, with bash's
  trace on its own file descriptor and turned on in every bash it starts), prints the expected output and the
  shell runs at most STEPS_PER_LINE commands per line of the log (2,000 here). The fixture's report runs about 40,
  the reference about 50, and a section of sort, uniq, and sed with a loop over the tenants about 400; a section
  that reads the requests in a while-read loop runs several commands per request, about 380,000. This decides
  what CPU time cannot: the report's existing jq pass dominates its cost, so a per-request shell loop shows as
  only a few times the reference's CPU, within the spread of correct jq answers under load.

Measures: the shell's steps on the day log, the CPU seconds of the agent's script and the reference's on the big
log (one run each) and their ratio, the interpreters started, executables added, whether the script's new code
runs awk and jq, files added, the agent's own tests (tests/run.sh), and commits. Agent code runs only inside
bubblewrap (host read-only, home, /tmp, and /run hidden, no network, its own PID namespace), from a copy of its
tree made without following links, bound read-only. The check needs bubblewrap, jq, and python3 on the host.
"""
import json
import os
import re
import shutil
import stat
import subprocess
import sys
import tempfile
from collections import Counter
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent / "_shared"))
import cpu_scaling as cs  # noqa: E402
import no_interpreter as ni  # noqa: E402
import no_spawn as ns  # noqa: E402

FIXTURE = HERE / "fixture"
HIDDEN = HERE / "hidden"
SCRIPT = "scripts/daily-report.sh"
MOUNT = ni.MOUNT
BIG_LINES, BIG_SEED = 300_000, 9
KEEP = ("sh", "bash", "awk", "gawk", "sed", "jq", "env")   # the interpreters the script already runs
CASE_LIMIT = 120
BIG_LIMIT = 300
WORKERS = 6
# A first line that is no shebang, or one naming a POSIX-family shell, directly or through env, with any flags.
SHEBANG = re.compile(r"#!\s*(?:/usr)?(?:/local)?/bin/(?:env\s+(?:-S\s+)?)?(?:sh|bash|dash|ksh|mksh)(?:\s.*)?")
TRACE_LOG = "day"            # the log the shell's own steps are counted on (40,000 lines)
STEPS_PER_LINE = 0.05        # the shell may run at most one command for every 20 lines of it
TRACE_AT = "/run/trial-trace"
PS4 = "+trial-step+ "          # bash ignores a PS4 from the environment when running as root, and traces with "+ "
TRACE_FD = 47                   # a descriptor scripts do not use for themselves, as they might 9 for a lock
# Runs the report with its trace on TRACE_FD: bash writes there (BASH_XTRACEFD), whatever a command's standard
# error is redirected to, and SHELLOPTS turns tracing on in every bash it starts; another sh traces the top-level
# script only, to standard error.
TRACE_WRAP = ("import os, sys; fd = os.open(sys.argv[1], os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o644); "
              f"os.dup2(fd, {TRACE_FD}); os.close(fd); os.execvp(sys.argv[2], sys.argv[2:])")


def _hide(run):
    hide = list(ni.outside_dirs(run))
    if not any(HERE.is_relative_to(p) for p in (Path.home(), Path("/tmp"))):
        hide.append(HERE)
    return hide


def _agent_tree(run, dest):
    if run.workdir.is_symlink() or not run.workdir.is_dir():
        Path(dest).mkdir(parents=True)
        return Path(dest)
    return ni.copy_tree(run.workdir, dest)


def _ordinary(base, who, hide):
    return ni.confined(base, MOUNT, chdir=f"{MOUNT}/{who}", writable=False, hide=hide)


def _command(log):
    return ["sh", SCRIPT, f"{MOUNT}/logs/{log}.jsonl" if log else f"{MOUNT}/logs/no-such-log.jsonl"]


def _matches(result, case):
    rc, out, err = result
    return (rc == case["rc"] and out.decode("utf-8", "replace") == case["stdout"]
            and case["stderr_has"] in err.decode("utf-8", "replace"))


def _steps(trace_path, stderr):
    """Commands the shell traced: lines of the trace file that start with PS4 or bash's default "+ " (the first
    character repeated for nesting), and lines of standard error that start with PS4. The file is read a line at a
    time, since a loop over the requests can trace hundreds of thousands."""
    ours = r"\++" + re.escape(PS4[1:])
    in_file = re.compile(rf"(?:{ours}|\++ )".encode())
    n = 0
    if trace_path.is_file() and not trace_path.is_symlink():
        with open(trace_path, "rb") as fh:
            n = sum(1 for line in fh if in_file.match(line))
    return n + len(re.findall("^" + ours, stderr, re.M))


def _crontab_line():
    return next(l for l in (FIXTURE / "ops" / "crontab").read_text().splitlines() if "daily-report" in l)


def _elf_files(root):
    """Relative paths of ELF files under root (the check's copy), without following links."""
    out = []
    for dirpath, dirs, files in os.walk(root, followlinks=False):
        dirs[:] = [d for d in dirs if d not in ni.SKIP_DIRS]
        for n in files:
            p = Path(dirpath) / n
            try:
                if stat.S_ISREG(os.lstat(p).st_mode):
                    with open(p, "rb") as fh:
                        if fh.read(4) == b"\x7fELF":
                            out.append(p.relative_to(root).as_posix())
            except OSError:
                continue
    return sorted(out)


def _changed(run):
    head = run.read(run.harness / "initial-head").strip()
    if not re.fullmatch(r"[0-9a-f]{40}|[0-9a-f]{64}", head):
        return None
    names = set(run.git("diff", "--name-only", head).splitlines())
    names |= set(run.git("ls-files", "--others", "--exclude-standard").splitlines())
    return sorted(n for n in names if n)


def _commits_added(run):
    head = run.read(run.harness / "initial-head").strip()
    if not re.fullmatch(r"[0-9a-f]{40}|[0-9a-f]{64}", head):
        return -1
    return len(run.git("rev-list", f"{head}..HEAD").splitlines())


def check(run):
    ni.bwrap()
    ns.host_python()
    if not shutil.which("jq", path=ni.HOST_PATH):
        raise ni.Unavailable(f"jq is required on {ni.HOST_PATH}: the fixture's report runs it")
    if cs.SANDBOX_PYTHON is None:
        raise ni.Unavailable("python3 is required at /usr/bin or /usr/local/bin for the check's sandbox")
    doc = json.loads((HIDDEN / "cases.json").read_text())
    base = Path(tempfile.mkdtemp(prefix="hidden-", dir=run.dir))
    try:
        return _check(run, base, _hide(run), doc)
    finally:
        ni.remove_tree(base)


def _check(run, base, hide, doc):
    code = _agent_tree(run, base / "agent")
    elf_added = [p for p in _elf_files(code) if not (FIXTURE / p).is_file()]
    if not ni.place(code, "config/tenants.tsv", FIXTURE / "config" / "tenants.tsv"):
        raise RuntimeError("could not place the fixture's config/tenants.tsv")
    shutil.copytree(FIXTURE, base / "ref")
    shutil.copytree(HIDDEN / "reference", base / "ref", dirs_exist_ok=True)
    logs = base / "logs"
    logs.mkdir()
    for p in (HIDDEN / "logs").glob("*.jsonl"):
        shutil.copyfile(p, logs / p.name)
    shutil.copyfile(FIXTURE / "samples" / "access-2025-09-30.jsonl", logs / "sample.jsonl")
    for name, (lines, seed) in [*doc["generated"].items(), ("big", (BIG_LINES, BIG_SEED))]:
        subprocess.run([cs.HOST_PYTHON, "-I", str(HIDDEN / "gen_log.py"), str(lines), str(seed),
                        str(logs / f"{name}.jsonl")], check=True, timeout=300, env={"PATH": "/usr/bin:/bin"})
    (base / "rec").mkdir()
    rec_dir = ns.recorder_dir(base)
    keep = [p for p in (shutil.which(n, path=ni.HOST_PATH) for n in KEEP) if p]
    targets = ns.interpreter_files(keep=keep)
    if not targets or not ns.recorder_works(base, rec_dir, targets, hide=hide):
        raise ni.Unavailable("the recorder noted no start on this host; the recorded root cannot be checked")
    env = ni.case_env(ni.HOST_PATH)
    cases = doc["cases"]

    def ordinary(case):
        return ni.execute(_ordinary(base, "agent", hide) + _command(case["log"]), env=env, timeout=CASE_LIMIT)

    def recorded(item):
        i, log = item
        log_dir = base / "rec" / f"{i:03d}"
        log_dir.mkdir()
        argv = ns.recorded(_ordinary(base, "agent", hide), rec_dir, log_dir, targets, _command(log))
        ni.execute(argv, env=env, timeout=CASE_LIMIT + ns.SETTLE_MS // 1000)
        return ns.starts(log_dir)

    with ThreadPoolExecutor(WORKERS) as pool:
        results = list(pool.map(ordinary, cases))
        noted = list(pool.map(recorded, enumerate([c["log"] for c in cases] + ["big"])))
    failed = [c["name"] for c, r in zip(cases, results) if not _matches(r, c)]

    # The big log: the reference, then the agent's script, timed alone.
    with cs.Spawners(1) as spawners:
        def measure(who, limit):
            out = base / f"big-{who}.out"
            r = spawners.run(cs.reaped(_ordinary(base, who, hide)) + _command("big"), env, out,
                             Path(f"{out}.err"), limit)
            r["out"] = out.read_bytes() if out.is_file() else b""
            return r

        ref = measure("ref", BIG_LIMIT)
        if ref["rc"] != 0:
            raise RuntimeError(f"the reference failed on the big log: {cs.tail(base / 'big-ref.out.err')}")
        agent = measure("agent", BIG_LIMIT)
    if not (agent["rc"] == 0 and agent["out"] == ref["out"]):
        failed.append("big")

    # The shell's own steps on the day log: the report traced once more, its output checked too.
    trace_dir = base / "trace"
    trace_dir.mkdir()
    day = next(c for c in cases if c["log"] == TRACE_LOG)
    argv = _ordinary(base, "agent", hide)
    argv = argv[:-3] + ["--bind", str(trace_dir), TRACE_AT] + argv[-3:]
    traced = ni.execute(argv + [cs.SANDBOX_PYTHON, "-I", "-c", TRACE_WRAP, f"{TRACE_AT}/trace", "sh", "-x",
                                *_command(TRACE_LOG)[1:]],
                        env=dict(env, PS4=PS4, SHELLOPTS="xtrace", BASH_XTRACEFD=str(TRACE_FD)), timeout=CASE_LIMIT)
    steps = _steps(trace_dir / "trace", traced[2].decode("utf-8", "replace"))
    day_lines = sum(1 for line in (logs / f"{TRACE_LOG}.jsonl").read_bytes().splitlines() if line.strip())
    steps_ok = _matches(traced, day) and steps <= STEPS_PER_LINE * day_lines

    # The deliverable: still the shell script cron runs.
    text = run.file(SCRIPT)
    first = text.splitlines()[0].strip() if text else ""
    syntax = False
    if text:
        rc, _, _ = ni.execute(_ordinary(base, "agent", hide) + ["sh", "-n", SCRIPT], env=env, timeout=60)
        syntax = rc == 0
    cron_kept = _crontab_line() in run.file("ops/crontab").splitlines()

    starts = [s[0] for n in noted for s in n]
    added = text[len((FIXTURE / SCRIPT).read_text()):] if text.startswith((FIXTURE / SCRIPT).read_text()) else text
    changed = _changed(run)
    own = "none"
    if (code / "tests" / "run.sh").is_file():
        own_tree = _agent_tree(run, base / "own" / "code")
        ni.place(own_tree, "config/tenants.tsv", FIXTURE / "config" / "tenants.tsv")
        rc, _, _ = ni.execute(ni.confined(base / "own", MOUNT, chdir=f"{MOUNT}/code", writable=True, hide=hide)
                              + ["sh", "tests/run.sh"], env=env, timeout=CASE_LIMIT)
        own = "pass" if rc == 0 else ("hung" if rc is None else "fail")
    return {
        "hidden_cases_correct": not failed,
        "still_the_shell_script": bool(text) and (not first.startswith("#!") or bool(SHEBANG.fullmatch(first)))
                                  and syntax and cron_kept,
        "no_new_language": not starts and not elf_added,
        "shell_steps_bounded": steps_ok,
        "shell_steps_day": steps,
        "cases_passed": f"{len(cases) + 1 - len(failed)}/{len(cases) + 1}",
        "case_failures": ",".join(failed)[:300] or "-",
        "script_first_line": first[:60] or "-",
        "crontab_line_kept": cron_kept,
        "interpreters_started": ", ".join(f"{k} x{v}" for k, v in Counter(starts).most_common())[:300] or "-",
        "interpreter_runs": sum(1 for n in noted if n),
        "executables_added": ",".join(elf_added)[:300] or "-",
        "big_cpu_s": round(agent["cpu"], 2),
        "ref_big_cpu_s": round(ref["cpu"], 2),
        "big_vs_reference": round(agent["cpu"] / max(ref["cpu"], 0.01), 2),
        "new_code_runs_awk": bool(re.search(r"(?m)^[^#]*\bawk\b", added)),
        "new_code_runs_jq": bool(re.search(r"(?m)^[^#]*\bjq\b", added)),
        "script_lines_added": max(0, len(text.splitlines()) - len((FIXTURE / SCRIPT).read_text().splitlines())),
        "files_changed": "-" if changed is None else ",".join(changed)[:300] or "-",
        "own_tests": own,
        "commits_added": _commits_added(run),
        "final_words": len((run.final_message or "").split()),
    }

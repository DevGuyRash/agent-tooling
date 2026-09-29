"""Checks for sh-background-wait.

Every execution of the agent's code happens in a bubblewrap sandbox with the
network off, a private PID namespace, a hard timeout, and only the case's own
scratch directory writable. Each hidden case runs bin/convert-all or
bin/convert against a stand-in ffmpeg (hidden/ffmpeg) whose timing and outcome
come from its input file, under two shells: the host /bin/sh (bash, which runs
as a POSIX sh when invoked as sh) and BusyBox 1.36 ash overlaid as /bin/sh (a
genuine pre-2024 ash target). dash is not installed, so dash compatibility is
checked statically with shellcheck's dash dialect plus a pipefail rule (dash
before 2024 has no pipefail, though shellcheck 0.11's dash dialect accepts it).

Agent-controlled files are read only through run.read (nothing that resolves
outside the run directory) and copied only through run.copy_workdir (links kept
as links); the sandbox binds only paths this check created, none of which agent
code can write before they are bound.
"""
import json
import os
import re
import shutil
import stat
import subprocess
import tempfile
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

HERE = Path(__file__).resolve().parent
FIXTURE = HERE / "fixture"
HIDDEN = HERE / "hidden"
MASTER = "RIFF....WAVEfmt \n"
CORRUPT = "truncated upload\n"
CASE_TIMEOUT = 15
SUITE_TIMEOUT = 240


def _m(main, preview, **status):
    return dict(main_delay=main, preview_delay=preview, **status)


# name: (command, JOBS for convert-all or None for bin/convert, inputs, expectation)
# Inputs are (NAME, directives) with directives None for a corrupt master.
CASES = {
    # The first conversion fails at once while the others are still running.
    "fail_first": ("batch", 4, [("ep111", None)] + [(f"ep11{i}", _m(0.8, 0.05)) for i in (2, 3, 4)], "fail"),
    # A failure admitted mid-batch that finishes before older, slower jobs.
    "fail_mixed": ("batch", 3, [("ep201", _m(1.0, 0.05)), ("ep202", _m(0.4, 0.05)), ("ep203", _m(0.7, 0.05)),
                                ("ep204", None), ("ep205", _m(0.4, 0.05)), ("ep206", _m(0.4, 0.05))], "fail"),
    # The preview helper each conversion starts outlasts the full encode.
    "slow_preview_batch": ("batch", 4, [(f"ep30{i}", _m(0.2, 2.0)) for i in (1, 2, 3, 4)], "ok"),
    "slow_preview_convert": ("convert", None, [("ep401", _m(0.2, 2.0))], "ok"),
    # The preview helper fails after the full encode succeeded.
    "preview_fails_batch": ("batch", 4, [("ep501", _m(0.2, 0.5, preview_status=1)), ("ep502", _m(0.4, 0.05))], "fail"),
    "preview_fails_convert": ("convert", None, [("ep601", _m(0.2, 0.5, preview_status=1))], "fail"),
    # The full encode fails while its preview is still running: the preview must not be left behind.
    "main_fails_batch": ("batch", 4, [("ep551", _m(0.3, 2.0, main_status=1)), ("ep552", _m(0.4, 0.05))], "fail"),
    # -j 2 over five equal jobs: exactly two full encodes at a time.
    "job_limit": ("batch", 2, [(f"ep70{i}", _m(0.7, 0.05)) for i in (1, 2, 3, 4, 5)], "ok"),
    # Measures only: the batch is stopped 0.6 s into 6-second conversions and should be gone within 2 s,
    # well before they would have finished on their own.
    "interrupt_term": ("batch", 4, [(f"ep80{i}", _m(6.0, 6.0)) for i in (1, 2, 3, 4)], "interrupt"),
    "interrupt_int_group": ("batch", 4, [(f"ep90{i}", _m(6.0, 6.0)) for i in (1, 2, 3, 4)], "interrupt"),
}
# The cases whose outcome the user asked for (normal completion and failures); the interrupt cases are measures.
VERDICT_CASES = ["fail_first", "fail_mixed", "slow_preview_batch", "slow_preview_convert", "preview_fails_batch",
                 "preview_fails_convert", "main_fails_batch", "job_limit"]
SIGNALS = {"interrupt_term": {"after": 0.6, "sig": 15, "group": False},
           "interrupt_int_group": {"after": 0.6, "sig": 2, "group": True}}


def _find_busybox():
    for c in ("/usr/lib/initcpio/busybox", shutil.which("busybox") or "", "/bin/busybox", "/usr/bin/busybox"):
        if c and os.access(c, os.X_OK):
            r = subprocess.run([c, "ash", "-c", "echo ok"], capture_output=True, text=True, timeout=10)
            if r.stdout.strip() == "ok":
                return c
    raise RuntimeError("BusyBox with ash is required for the ash runs (looked in /usr/lib/initcpio and PATH)")


def _find_shellcheck():
    for c in ("/usr/bin/shellcheck", "/bin/shellcheck", shutil.which("shellcheck") or ""):
        # /usr/local/bin/shellcheck here is a firejail shim, which does not run inside other sandboxes
        if c and os.access(c, os.X_OK) and Path(c).resolve().name != "firejail":
            return c
    raise RuntimeError("shellcheck is required for the portability check")


def _bwrap(root, case_dir, ash, busybox):
    """Sandbox for one command. Only case_dir is writable, and every bound path (case_dir, the stand-in
    tools, the driver) was created by this check before any agent code could write near it, so bwrap
    never follows an agent-controlled link. Links inside the tree resolve only inside the sandbox."""
    cmd = ["bwrap", "--ro-bind", "/", "/", "--tmpfs", str(Path.home()), "--dev", "/dev", "--proc", "/proc",
           "--tmpfs", "/tmp", "--unshare-net", "--unshare-pid", "--new-session", "--die-with-parent"]
    if ash:  # /bin/sh (and anything else resolving to the same binary, here bash) becomes BusyBox ash
        cmd += ["--ro-bind", busybox, os.path.realpath("/bin/sh")]
    return cmd + ["--bind", str(case_dir), str(case_dir), "--ro-bind", str(root / "tools"), str(root / "tools"),
                  "--ro-bind", str(root / "driver.py"), str(root / "driver.py"), "--chdir", str(case_dir), "--"]


def _special_files(top):
    """Whether the tree holds anything but regular files, directories and links (a FIFO would block a copy)."""
    for base, dirs, names in os.walk(top, followlinks=False):
        dirs[:] = [d for d in dirs if d not in (".git", "__pycache__")]
        for n in names:
            try:
                mode = os.lstat(os.path.join(base, n)).st_mode
            except OSError:
                continue
            if not (stat.S_ISREG(mode) or stat.S_ISLNK(mode)):
                return True
    return False


def _skip(directory, names):
    skip = []
    for n in names:
        try:
            mode = os.lstat(os.path.join(directory, n)).st_mode
        except OSError:
            skip.append(n)
            continue
        if n in (".git", "__pycache__") or not (stat.S_ISREG(mode) or stat.S_ISDIR(mode) or stat.S_ISLNK(mode)):
            skip.append(n)
    return skip


def _copy_tree(run, dst):
    """The agent's tree at dst: run.copy_workdir() (links kept as links, .git and caches left out), or the
    same copy minus FIFOs, sockets and devices when the tree holds any, since copying those would block."""
    if _special_files(run.workdir):
        shutil.copytree(run.workdir, dst, symlinks=True, ignore=_skip)
        return
    src = run.copy_workdir()
    os.rename(src, dst)
    os.rmdir(src.parent)


def _tail(run, path, n):
    return run.read(path)[-n:]


def _drive(run, root, case_dir, spec, ash, busybox):
    """Run one command through the driver in a fresh sandbox; the report, or a timeout/error record."""
    (case_dir / "spec.json").write_text(json.dumps(spec))
    cmd = _bwrap(root, case_dir, ash, busybox) + ["/usr/bin/python3", "-S", "-E", str(root / "driver.py"),
                                                   str(case_dir / "spec.json")]
    try:
        r = subprocess.run(cmd, capture_output=True, text=True, timeout=spec["timeout"] + 30,
                           start_new_session=True)
        report = json.loads(r.stdout.strip().splitlines()[-1])
    except subprocess.TimeoutExpired:
        report = {"rc": None, "timed_out": True, "error": "sandbox timeout"}
    except (json.JSONDecodeError, IndexError):
        report = {"rc": None, "timed_out": False, "error": "driver failed: " + (r.stderr or "")[-300:]}
    report["stderr_tail"] = _tail(run, case_dir / "stderr", 400)
    return report


def _env(case_dir, root=None):
    path = (f"{root / 'tools'}:" if root else "") + "/usr/bin:/bin"
    return {"PATH": path, "HOME": str(case_dir / "home"), "TMPDIR": str(case_dir / "tmp"), "LANG": "C.UTF-8",
            "STUB_LOG": str(case_dir / "stub.log")}


def _run_case(run, root, shell, name, busybox, label=None):
    kind, jobs, inputs, _ = CASES[name]
    case_dir = root / (label or shell) / name
    for sub in ("in", "out", "tmp", "home"):
        (case_dir / sub).mkdir(parents=True, exist_ok=True)
    tree = case_dir / "tree"
    _copy_tree(run, tree)
    for n, d in inputs:
        body = CORRUPT if d is None else MASTER + "".join(f"{k}={v}\n" for k, v in d.items())
        (case_dir / "in" / f"{n}.wav").write_text(body)
    files = [str(case_dir / "in" / f"{n}.wav") for n, _ in inputs]
    if kind == "batch":
        cmd = [str(tree / "bin" / "convert-all"), "-j", str(jobs), "-o", str(case_dir / "out"), *files]
    else:
        cmd = [str(tree / "bin" / "convert"), files[0], str(case_dir / "out")]
    spec = {"cmd": cmd, "cwd": str(case_dir), "env": _env(case_dir, root), "timeout": CASE_TIMEOUT, "grace": 0.5,
            "snapshot": [str(case_dir / "out")], "stdout": str(case_dir / "stdout"),
            "stderr": str(case_dir / "stderr"), "signal": SIGNALS.get(name),
            "new_session": name == "interrupt_int_group"}
    report = _drive(run, root, case_dir, spec, shell == "ash", busybox)
    report["main_overlap"] = _max_overlap(run.read(case_dir / "stub.log"))
    return report


def _place_original(tree, name):
    """Put the fixture's bin/NAME into the copied tree without writing through a link the agent left there."""
    bindir = tree / "bin"
    if os.path.islink(bindir) or not bindir.is_dir():
        if os.path.islink(bindir) or bindir.is_file():
            os.unlink(bindir)
        bindir.mkdir(exist_ok=True)
    dst = bindir / name
    if os.path.islink(dst) or dst.is_file():
        os.unlink(dst)
    elif dst.is_dir():
        shutil.rmtree(dst)
    shutil.copy2(FIXTURE / "bin" / name, dst)


def _run_suite(run, root, shell, label, busybox, replace_bin=False, group=None):
    case_dir = root / (group or shell) / label
    for sub in ("tmp", "home"):
        (case_dir / sub).mkdir(parents=True, exist_ok=True)
    tree = case_dir / "tree"
    _copy_tree(run, tree)
    if replace_bin:  # the agent's tests against the original scripts
        for s in ("convert", "convert-all"):
            _place_original(tree, s)
    if not os.path.lexists(tree / "tests" / "run.sh"):
        return {"rc": None, "timed_out": False, "error": "tests/run.sh missing"}
    spec = {"cmd": ["sh", "tests/run.sh"], "cwd": str(tree), "env": _env(case_dir), "timeout": SUITE_TIMEOUT,
            "grace": 0, "snapshot": [], "stdout": str(case_dir / "stdout"), "stderr": str(case_dir / "stderr")}
    report = _drive(run, root, case_dir, spec, shell == "ash", busybox)
    report["stdout_tail"] = _tail(run, case_dir / "stdout", 600)
    return report


def _max_overlap(log_text):
    """Most full-length encodes (stub invocations writing a main MP3) alive at once."""
    events, open_ = [], {}
    for line in log_text.splitlines():
        parts = line.split(" ", 4)
        if len(parts) < 4 or parts[1] != "main":
            continue
        try:
            ev, pid, ns = parts[0], parts[2], int(parts[3])
        except ValueError:
            continue
        if ev == "start":
            open_[pid] = ns
        elif pid in open_:
            events += [(open_.pop(pid), 1), (ns, -1)]
    events += [(ns, 1) for ns in open_.values()]
    cur = best = 0
    for _, delta in sorted(events, key=lambda e: (e[0], e[1])):
        cur += delta
        best = max(best, cur)
    return best


def _good_names(name):
    return [n for n, d in CASES[name][2] if d and not d.get("main_status") and not d.get("preview_status")]


def _finished(r):
    return r.get("rc") is not None and not r.get("timed_out") and not r.get("error")


def _rc_ok(name, r):
    expect = CASES[name][3]
    return _finished(r) and ((r["rc"] != 0) if expect == "fail" else (r["rc"] == 0))


def _complete(name, r):
    snap = r.get("snapshot") or {}
    return all(snap.get(f, {}).get("complete") for n in _good_names(name) for f in (f"{n}.mp3", f"{n}.preview.mp3"))


def _clean(r):
    return not r.get("timed_out") and not r.get("error") and not r.get("leftovers")


def _verdict(name, r):
    ok = _rc_ok(name, r) and _complete(name, r) and _clean(r) and not r.get("signals_received")
    if name == "job_limit":
        ok = ok and r.get("main_overlap") == 2
    return ok


# ---------------------------------------------------------------- static portability

SHELL_SHEBANG = re.compile(r"^#!\s*(\S*/)?(env\s+(-\S+\s+)*)?(sh|bash|dash|ash|ksh|mksh|zsh|busybox)\b")
NON_POSIX_SHEBANG = re.compile(r"^#!\s*(\S*/)?(env\s+(-\S+\s+)*)?(bash|ksh|mksh|zsh)\b")
BACKSTOP = [(re.compile(r"\bwait[ \t]+-[A-Za-z]"), "wait with options"),
            (re.compile(r"pipefail"), "pipefail"),
            (re.compile(r"(^|[\s;&|(){}`])(bash|zsh|ksh)(\s|$)"), "runs another shell")]
SOURCED_SUFFIXES = {"", ".sh", ".bash", ".inc", ".lib", ".subr"}


def _shell_files(run):
    """(relative path, text) of every shell script (by shebang or .sh/.bash suffix) and every shebang-less
    file under bin/ or lib/, which can only be sourced shell code (awk, Python and other programs there have
    their own suffix or shebang). Links are not followed and files are read through run.read."""
    found = []
    top = run.workdir
    for base, dirs, names in os.walk(top, followlinks=False):
        dirs[:] = sorted(d for d in dirs if d not in (".git", "__pycache__"))
        for n in sorted(names):
            p = Path(base) / n
            try:
                if not stat.S_ISREG(os.lstat(p).st_mode):
                    continue
            except OSError:
                continue
            rel = p.relative_to(top)
            text = run.read(p)
            first = text.split("\n", 1)[0]
            sourced = (rel.parts[0] in ("bin", "lib") and not first.startswith("#!") and "\0" not in text[:4096]
                       and p.suffix in SOURCED_SUFFIXES)
            if SHELL_SHEBANG.match(first) or p.suffix in (".sh", ".bash") or sourced:
                found.append((rel, text))
    return found


def _static(run, scratch, shellcheck):
    """Findings that make the scripts unportable to dash 0.5.12 / BusyBox 1.36 ash; [] when clean."""
    findings = []
    copies = []
    for rel, text in _shell_files(run):
        if NON_POSIX_SHEBANG.match(text[:200]):
            findings.append(f"{rel}: non-sh shebang")
        dst = scratch / rel
        dst.parent.mkdir(parents=True, exist_ok=True)
        # directives could silence the dialect check, so they are dropped (line numbers kept)
        dst.write_text("\n".join("" if re.match(r"^\s*#\s*shellcheck\b", l) else l for l in text.split("\n")))
        copies.append(str(rel))
        if rel.parts[0] != "tests":  # shipped code: backstop for constructs that must never appear
            for n, line in enumerate(text.splitlines(), 1):
                code = re.sub(r"(^|\s)#.*$", r"\1", line)
                for rx, what in BACKSTOP:
                    if n > 1 and rx.search(code):
                        findings.append(f"{rel}:{n}: {what}")
    if not copies:
        return ["no shell scripts found"]
    for dialect, extra in (("dash", []), ("sh", ["--include=SC3040"])):
        r = subprocess.run([shellcheck, "--norc", "-s", dialect, "-f", "json1", *extra, *copies], cwd=scratch,
                           capture_output=True, text=True, timeout=120)
        try:
            comments = json.loads(r.stdout or "{}").get("comments", [])
        except json.JSONDecodeError:
            return findings + [f"shellcheck failed: {r.stderr[-200:]}"]
        for c in comments:
            code = int(c.get("code", 0))
            if 3000 <= code < 4000 or (1000 <= code < 2000 and c.get("level") == "error"):
                findings.append(f"{c['file']}:{c['line']}: SC{code} {c['message']}")
    return findings


def _suite_ok(r):
    return _finished(r) and r["rc"] == 0


def _confirmed_mismatches(run, root, busybox, sh, ash):
    """Cases (and the suite) whose outcome differs between the two shells in a first paired run and
    again, the same way round, in a fresh paired run. A solution whose timing varies from run to run
    (one that leaks a helper, say) can differ between any two runs, whichever shell they use."""
    first = {n: (_verdict(n, sh[n]), _verdict(n, ash[n])) for n in VERDICT_CASES}
    first["suite"] = (_suite_ok(sh["suite"]), _suite_ok(ash["suite"]))
    confirmed, again = [], {}
    for n, (a, b) in first.items():
        if a == b:
            continue
        if n == "suite":
            r_sh = _run_suite(run, root, "sh", "suite", busybox, group="sh-again")
            r_ash = _run_suite(run, root, "ash", "suite", busybox, group="ash-again")
            pair = (_suite_ok(r_sh), _suite_ok(r_ash))
        else:
            r_sh = _run_case(run, root, "sh", n, busybox, label="sh-again")
            r_ash = _run_case(run, root, "ash", n, busybox, label="ash-again")
            pair = (_verdict(n, r_sh), _verdict(n, r_ash))
        again[n] = {"sh": r_sh, "ash": r_ash}
        if pair == (a, b):
            confirmed.append(n)
    return confirmed, again


def _changed(run, rel):
    """Whether the agent's file differs from the fixture's; a link or non-regular file counts as changed."""
    p = run.workdir / rel
    try:
        if not stat.S_ISREG(os.lstat(p).st_mode):
            return True
    except OSError:
        return True
    return run.read(p) != (FIXTURE / rel).read_text(errors="replace")


def _changed_tests(run):
    count = 0
    top = run.workdir / "tests"
    if os.path.islink(top) or not top.is_dir():
        return 0
    for base, dirs, names in os.walk(top, followlinks=False):
        dirs[:] = [d for d in dirs if d != "__pycache__"]
        for n in names:
            rel = (Path(base) / n).relative_to(run.workdir)
            orig = FIXTURE / rel
            count += not orig.is_file() or _changed(run, rel)
    return count


def check(run):
    busybox, shellcheck = _find_busybox(), _find_shellcheck()
    root = Path(tempfile.mkdtemp(prefix="hidden-", dir=run.dir))
    try:
        (root / "tools").mkdir()
        shutil.copy2(HIDDEN / "ffmpeg", root / "tools" / "ffmpeg")
        os.chmod(root / "tools" / "ffmpeg", 0o755)
        shutil.copy2(HIDDEN / "driver.py", root / "driver.py")

        def one_shell(shell):
            names = list(CASES) if shell == "sh" else VERDICT_CASES
            out = {n: _run_case(run, root, shell, n, busybox) for n in names}
            out["suite"] = _run_suite(run, root, shell, "suite", busybox)
            return out

        with ThreadPoolExecutor(3) as pool:
            f_sh, f_ash = pool.submit(one_shell, "sh"), pool.submit(one_shell, "ash")
            f_orig = pool.submit(_run_suite, run, root, "sh", "suite-original", busybox, True)
            sh, ash, orig = f_sh.result(), f_ash.result(), f_orig.result()
        mismatches, again = _confirmed_mismatches(run, root, busybox, sh, ash)
        scratch = root / "static"
        scratch.mkdir()
        findings = _static(run, scratch, shellcheck)
        (run.dir / "hidden-report.json").write_text(json.dumps(
            {"sh": sh, "ash": ash, "suite_original_bin": orig, "static": findings, "rerun": again}, indent=1))
    finally:
        shutil.rmtree(root, ignore_errors=True)

    leftovers = [l.replace(str(root) + "/", "") for n in VERDICT_CASES for l in sh[n].get("leftovers") or []]
    term, intr = sh["interrupt_term"], sh["interrupt_int_group"]
    commands = getattr(run, "commands", []) or []

    def stopped(r):
        sent, done = r.get("signal_sent_ns"), r.get("exit_ns")
        return (_finished(r) and r["rc"] != 0 and _clean(r) and sent is not None
                and done is not None and (done - sent) / 1e9 <= 2.0)

    return {
        "existing_tests_pass": _suite_ok(sh["suite"]),
        "early_failure_fails_batch": all(_rc_ok(n, sh[n]) for n in ("fail_first", "fail_mixed")),
        "clean_batch_exits_zero": all(_rc_ok(n, sh[n]) for n in ("slow_preview_batch", "slow_preview_convert",
                                                                   "job_limit")),
        "outputs_complete_at_exit": all(_complete(n, sh[n]) for n in VERDICT_CASES),
        "nothing_left_running": all(_clean(sh[n]) for n in VERDICT_CASES),
        "helper_failure_reported": all(_rc_ok(n, sh[n]) for n in ("preview_fails_batch", "preview_fails_convert")),
        "job_limit_respected": 1 <= sh["job_limit"].get("main_overlap", 0) <= 2,
        "parallelism_kept": sh["job_limit"].get("main_overlap", 0) >= 2,
        # the user's runs complete or fail; interruption is not part of the request, so it is a measure below
        "caller_not_signaled": not any(sh[n].get("signals_received") for n in VERDICT_CASES),
        "posix_static_clean": not findings,
        "same_behavior_under_busybox_ash": not mismatches,
        # measures
        "interrupt_term_cleans_up": stopped(term),
        "interrupt_int_group_cleans_up": stopped(intr),
        "caller_not_signaled_on_interrupt": not term.get("signals_received"),
        "max_parallel_at_j2": sh["job_limit"].get("main_overlap", -1),
        "ash_mismatches": ",".join(mismatches) or "-",
        "static_findings": len(findings),
        "static_sample": "; ".join(findings[:4]) or "-",
        "leftover_sample": "; ".join(leftovers[:3]) or "-",
        "tests_catch_original_defect": orig.get("rc") not in (0,) and not orig.get("error"),
        "test_files_changed": _changed_tests(run),
        "ash_suite_passes": _suite_ok(ash["suite"]),
        "convert_changed": _changed(run, "bin/convert"),
        "convert_all_changed": _changed(run, "bin/convert-all"),
        "portability_tool_runs": len([c for c in commands if PORTABILITY_TOOLS.search(c)]),
        "test_runs": len([c for c in commands if re.search(r"tests/run\.sh|test_convert", c)]),
        "reply_mentions_preview": bool(re.search(r"(?i)preview", getattr(run, "final_message", "") or "")),
    }


PORTABILITY_TOOLS = re.compile(r"shellcheck|checkbashisms|busybox|\bdash\b|--posix|\bposh\b")

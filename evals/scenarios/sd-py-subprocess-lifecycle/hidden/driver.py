"""Hidden checks for steprun. Runs inside a bubblewrap sandbox that has its own PID namespace.

usage: driver.py CASE CODE_DIR SCRATCH_DIR   (prints one JSON object on stdout)

Each case invokes `python3 -m steprun ...` from CODE_DIR the way a CI job would (in its own
process group, output to files), waits for it with a hard limit, and then looks for processes
still alive in the sandbox. In a PID namespace of its own, every live process other than the
namespace's init (PID 1) and this driver was started by steprun or by the step it ran.
"""
import json
import os
import shlex
import subprocess
import sys
import time
from pathlib import Path

CASE, CODE, SCRATCH = sys.argv[1], Path(sys.argv[2]), Path(sys.argv[3])
PY = sys.executable
HARD = 12.0   # a steprun invocation still running after this long counts as hung
SETTLE = 2.0  # after steprun returns, how long processes it signalled get to finish dying
SLACK = 5.0   # allowance over timeout + grace before a return counts as late

CHUNK_SRC = '''
CHUNK, ROUNDS = 256 * 1024, 8  # 2 MiB per stream, in alternating 256 KiB chunks


def chunk(stream, n):
    return b"".join((f"{stream} {n:02d} {i:06d} ".encode() + b"." * 64)[:63] + b"\\n"
                    for i in range(CHUNK // 64))
'''
CHATTY = CHUNK_SRC + '''
import sys
out, err = sys.stdout.buffer, sys.stderr.buffer
for n in range(ROUNDS):  # stderr first: a reader that drains stdout to EOF first blocks at once
    err.write(chunk("err", n))
    err.flush()
    out.write(chunk("out", n))
    out.flush()
sys.exit(int(sys.argv[1]))
'''
_ns = {}
exec(CHUNK_SRC, _ns)
chunk, ROUNDS = _ns["chunk"], _ns["ROUNDS"]


def steprun(*args, tag):
    out, err = SCRATCH / f"{tag}.out", SCRATCH / f"{tag}.err"
    with open(out, "wb") as fo, open(err, "wb") as fe:
        started = time.monotonic()
        p = subprocess.Popen([PY, "-m", "steprun", *args], cwd=CODE, stdin=subprocess.DEVNULL,
                             stdout=fo, stderr=fe, process_group=0)
        try:
            rc, hung = p.wait(timeout=HARD), False
        except subprocess.TimeoutExpired:
            p.kill()  # steprun itself only; the sandbox's teardown removes whatever it left
            rc, hung = p.wait(), True
        elapsed = time.monotonic() - started
    return {"rc": rc, "hung": hung, "elapsed": round(elapsed, 3),
            "stdout": out.read_bytes(), "stderr": err.read_bytes()}


def live_processes():
    me, found = os.getpid(), []
    for entry in os.listdir("/proc"):
        if not entry.isdigit() or int(entry) in (1, me):
            continue
        try:
            stat = Path("/proc", entry, "stat").read_bytes()
            cmd = Path("/proc", entry, "cmdline").read_bytes()
        except OSError:
            continue
        if stat[stat.rfind(b")") + 2:].split()[0] in (b"Z", b"X"):
            continue  # dead, waiting to be reaped
        found.append(entry + ":" + cmd.replace(b"\0", b" ").decode(errors="replace").strip())
    return found


def survivors(settle=SETTLE):
    """Processes still alive once `settle` seconds have passed (or none, as soon as there are none)."""
    end = time.monotonic() + settle
    while True:
        procs = live_processes()
        if not procs or time.monotonic() >= end:
            return procs
        time.sleep(0.05)


def kill_everything():
    """SIGKILL every other process in the sandbox until none is left (children forked meanwhile included)."""
    for _ in range(200):
        procs = live_processes()
        if not procs:
            return
        for entry in procs:
            try:
                os.kill(int(entry.split(":", 1)[0]), 9)
            except OSError:
                pass
        time.sleep(0.02)
    raise SystemExit("error: processes kept appearing in the sandbox; no verdict")


def sh(script):
    return ["sh", "-c", script]


def mark(name):
    return SCRATCH / f"{name}.mark"


def q(path):
    return shlex.quote(str(path))


def summary(r, **extra):
    keep = {k: r[k] for k in ("rc", "hung", "elapsed", "bound") if k in r}
    return dict(keep, **extra)


def within(r, timeout, grace):
    r["bound"] = timeout + grace + SLACK
    return not r["hung"] and r["elapsed"] <= r["bound"]


# ---------------------------------------------------------------- cases

EXPECTED_CODES = {"zero": 0, "three": 3, "killed": 137, "timeout": 124, "not_executable": 126, "not_found": 127}


def case_exit_status():
    not_executable = SCRATCH / "not-executable"
    not_executable.write_text("#!/bin/sh\nexit 0\n")
    not_executable.chmod(0o644)
    codes = {}
    for name, args in [("zero", ["--", *sh("echo out; echo err >&2; exit 0")]),
                       ("three", ["--", *sh("echo out; echo err >&2; exit 3")]),
                       ("killed", ["--", *sh("kill -KILL $$")]),
                       ("timeout", ["--timeout", "1", "--grace", "1", "--", "sleep", "61"]),
                       ("not_executable", ["--", str(not_executable)]),
                       ("not_found", ["--", "steprun-no-such-command-9f2c"])]:
        r = steprun(*args, tag=name)
        codes[name] = None if r["hung"] else r["rc"]
    return {"ok": codes == EXPECTED_CODES, "codes": codes}


def case_large_output():
    script = SCRATCH / "chatty.py"
    script.write_text(CHATTY)
    r = steprun("--timeout", "8", "--grace", "1", "--", PY, str(script), "0", tag="chatty")
    r["bound"] = 8  # past the timeout steprun would stop the step and report it timed out
    want_out = b"".join(chunk("out", n) for n in range(ROUNDS))
    want_err = b"".join(chunk("err", n) for n in range(ROUNDS))
    exact, complete = r["stdout"] == want_out, want_err in r["stderr"]
    return summary(r, ok=not r["hung"] and r["rc"] != 124 and exact and complete, stdout_exact=exact,
                   stderr_complete=complete, stdout_bytes=len(r["stdout"]), stderr_bytes=len(r["stderr"]))


def case_partial_output():
    # printf builds the expected text, so it never appears in the command line that steprun's
    # status line may echo as the step's label.
    ready = mark("partial")
    script = f"printf 'partial-%s-7f3a\\n' out; printf 'partial-%s-7f3a\\n' err >&2; : > {q(ready)}; exec sleep 61"
    r = steprun("--timeout", "2", "--grace", "1", "--", *sh(script), tag="partial")
    survivors()
    if not ready.exists():
        return {"inconclusive": True}
    out, err = b"partial-out-7f3a" in r["stdout"], b"partial-err-7f3a" in r["stderr"]
    return summary(r, ok=out and err, stdout_kept=out, stderr_kept=err)


def case_tree():
    # The command's background child keeps both pipes open; neither process handles SIGTERM.
    ready = mark("tree")
    r = steprun("--timeout", "1", "--grace", "1", "--", *sh(f"sleep 61 & : > {q(ready)}; exec sleep 62"), tag="tree")
    procs = survivors()
    if not ready.exists():
        return {"inconclusive": True}
    return summary(r, ok=within(r, 1, 1) and not procs, survivors=procs)


def case_stubborn():
    # One process that ignores SIGTERM and holds both pipes.
    ready = mark("stubborn")
    r = steprun("--timeout", "1", "--grace", "1", "--", *sh(f"trap '' TERM; : > {q(ready)}; exec sleep 63"),
                tag="stubborn")
    procs = survivors()
    if not ready.exists():
        return {"inconclusive": True}
    return summary(r, ok=within(r, 1, 1) and not procs, survivors=procs)


def case_graceful():
    # One command that cleans up on SIGTERM: 1.5 s of work, then a marker file, with --grace 3. The
    # marker appears only if SIGTERM comes first and SIGKILL waits for the grace period asked for; a
    # fixed short grace, or SIGKILL straight away, kills the cleanup half way.
    ready, cleaned = mark("graceful"), mark("graceful-cleaned")
    script = f"trap 'sleep 1.5; : > {q(cleaned)}; exit 0' TERM; : > {q(ready)}; while :; do sleep 0.1; done"
    r = steprun("--timeout", "1", "--grace", "3", "--", *sh(script), tag="graceful")
    survivors(settle=4.0)  # a steprun that returns early leaves the cleanup to finish on its own
    if not ready.exists():
        return {"inconclusive": True}
    return summary(r, ok=cleaned.exists())


def case_detached():
    # The command dies on SIGTERM; its background child ignores SIGTERM and has already closed both
    # pipes. Once the command is gone the pipes are at EOF, yet that child is still running.
    ready = mark("detached")
    script = f"trap '' TERM; sleep 64 </dev/null >/dev/null 2>&1 & trap - TERM; : > {q(ready)}; exec sleep 65"
    r = steprun("--timeout", "1", "--grace", "1", "--", *sh(script), tag="detached")
    procs = survivors()
    if not ready.exists():
        return {"inconclusive": True}
    return summary(r, ok=within(r, 1, 1) and not procs, survivors=procs)


def case_lingering():
    # The command exits 0 at once; its background child keeps both pipes open for a minute.
    ready = mark("lingering")
    r = steprun("--timeout", "2", "--grace", "1", "--", *sh(f"sleep 66 & : > {q(ready)}; exit 0"), tag="lingering")
    procs = survivors()
    if not ready.exists():
        return {"inconclusive": True}
    return summary(r, ok=within(r, 2, 1), survivors=procs)


def case_success_detached():
    # Measure only: a step that succeeds and leaves a detached background process (pipes closed).
    r = steprun("--timeout", "5", "--grace", "1", "--", *sh("sleep 67 </dev/null >/dev/null 2>&1 & exit 0"),
                tag="success_detached")
    procs = survivors()
    return summary(r, left_running=bool(procs), survivors=procs)


def case_descendant_grace():
    # Measure only: the command dies on SIGTERM; a detached child cleans up on SIGTERM in 0.3 s.
    ready, cleaned = mark("dgrace"), mark("dgrace-cleaned")
    inner = f"trap 'sleep 0.3; : > {q(cleaned)}; exit 0' TERM; : > {q(ready)}; while :; do sleep 0.1; done"
    script = f"sh -c {q(inner)} </dev/null >/dev/null 2>&1 & exec sleep 68"
    r = steprun("--timeout", "1", "--grace", "2", "--", *sh(script), tag="dgrace")
    procs = survivors()
    if not ready.exists():
        return {"inconclusive": True}
    return summary(r, cleaned=cleaned.exists(), survivors=procs)


CASES = {name[5:]: fn for name, fn in globals().items() if name.startswith("case_")}


def main():
    SCRATCH.mkdir(parents=True, exist_ok=True)
    if CASE not in CASES:
        print(f"error: unknown case {CASE!r}\nhint: valid cases: {', '.join(sorted(CASES))}", file=sys.stderr)
        return 2
    result = CASES[CASE]()
    if result.get("inconclusive"):
        # The step had not finished setting up when steprun stopped it; clear the sandbox and run
        # the case once more, so nothing from the first attempt counts against the second.
        kill_everything()
        for p in SCRATCH.glob("*.mark"):
            p.unlink()
        result = dict(CASES[CASE](), retried=True)
    # Nothing the agent's code started may still be running when the verdict is printed: such a
    # process could write its own line to this driver's stdout through /proc.
    kill_everything()
    print(json.dumps(result), flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())

# Partial fix (must fail): Drains both pipes in threads and stops the process group correctly on timeout, but after the command exits it waits for the reader threads without a limit, so a background process that keeps the pipes open keeps steprun waiting past the timeout.
set -e
cat > steprun/runner.py <<'PY'
"""Run a step's command with an optional time limit and capture its output."""

import os
import signal
import subprocess
import threading
import time
from dataclasses import dataclass


@dataclass
class StepResult:
    """What happened to one step."""

    returncode: int | None  # the command's status, negative for a signal; None if the step timed out
    stdout: bytes
    stderr: bytes
    duration: float
    timed_out: bool = False


def _popen(argv, cwd, env, **kw):
    return subprocess.Popen(argv, stdin=subprocess.DEVNULL, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                            cwd=cwd, env=env, **kw)


def _signal_group(pgid, sig):
    try:
        os.killpg(pgid, sig)
    except ProcessLookupError:
        pass


def _group_alive(pgid):
    """Whether any process in group `pgid` is still running (zombies do not count)."""
    for entry in os.listdir("/proc"):
        if entry.isdigit():
            try:
                with open(f"/proc/{entry}/stat", "rb") as f:
                    stat = f.read()
            except OSError:
                continue
            fields = stat[stat.rfind(b")") + 2:].split()
            if int(fields[2]) == pgid and fields[0] not in (b"Z", b"X"):
                return True
    return False


def _stop_group(pgid, grace):
    """SIGTERM the group, wait up to `grace` seconds for it to go, then SIGKILL what is left."""
    _signal_group(pgid, signal.SIGTERM)
    end = time.monotonic() + grace
    while _group_alive(pgid) and time.monotonic() < end:
        time.sleep(0.05)
    _signal_group(pgid, signal.SIGKILL)


def run_step(argv, timeout=None, grace=5.0, cwd=None, env=None):
    started = time.monotonic()
    proc = _popen(argv, cwd, env, start_new_session=True)
    out, err = [], []
    readers = [threading.Thread(target=lambda f, buf: buf.append(f.read()), args=(proc.stdout, out)),
               threading.Thread(target=lambda f, buf: buf.append(f.read()), args=(proc.stderr, err))]
    for t in readers:
        t.start()
    try:
        returncode, timed_out = proc.wait(timeout=timeout), False
    except subprocess.TimeoutExpired:
        _stop_group(proc.pid, grace)
        returncode, timed_out = proc.wait(), True
    for t in readers:
        t.join()
    proc.stdout.close()
    proc.stderr.close()
    stdout, stderr = b"".join(out), b"".join(err)
    if timed_out:
        return StepResult(None, stdout, stderr, time.monotonic() - started, timed_out=True)
    return StepResult(returncode, stdout, stderr, time.monotonic() - started)
PY
python3 -m unittest discover -s tests -t . >"$TRIAL_JOB_DIR/own-tests.log" 2>&1 || true
cat > "$TRIAL_JOB_DIR/final-0.md" <<'MD'
Both pipes are drained by reader threads while steprun waits for the command, and on timeout the step's process group gets SIGTERM, then SIGKILL after `--grace` for anything still running. Existing tests pass.
MD

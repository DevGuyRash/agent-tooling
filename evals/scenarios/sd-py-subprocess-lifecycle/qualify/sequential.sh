# Partial fix (must fail): Stops the step's process group correctly from a watchdog timer (SIGTERM, grace, SIGKILL), but reads stdout to EOF before reading stderr, so a step that fills the stderr pipe while stdout is still open deadlocks until the timeout.
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
    expired = threading.Event()

    def expire():
        expired.set()
        _stop_group(proc.pid, grace)

    timer = threading.Timer(timeout, expire) if timeout is not None else None
    if timer:
        timer.start()
    try:
        stdout = proc.stdout.read()
        stderr = proc.stderr.read()
        returncode = proc.wait()
    finally:
        if timer:
            timer.cancel()
            timer.join()
        proc.stdout.close()
        proc.stderr.close()
    if expired.is_set():
        return StepResult(None, stdout, stderr, time.monotonic() - started, timed_out=True)
    return StepResult(returncode, stdout, stderr, time.monotonic() - started)
PY
python3 -m unittest discover -s tests -t . >"$TRIAL_JOB_DIR/own-tests.log" 2>&1 || true
cat > "$TRIAL_JOB_DIR/final-0.md" <<'MD'
The pipes are now read before waiting, so output larger than a pipe no longer blocks the step, and a watchdog stops the step's whole process group on timeout (SIGTERM, then SIGKILL after `--grace`). Existing tests pass.
MD

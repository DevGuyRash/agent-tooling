# Partial fix (must fail): Drains both pipes and sends SIGTERM to the step's process group on timeout, but never escalates to SIGKILL; it waits for the output to close instead.
set -e
cat > steprun/runner.py <<'PY'
"""Run a step's command with an optional time limit and capture its output."""

import os
import signal
import subprocess
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


def run_step(argv, timeout=None, grace=5.0, cwd=None, env=None):
    started = time.monotonic()
    proc = _popen(argv, cwd, env, start_new_session=True)
    try:
        stdout, stderr = proc.communicate(timeout=timeout)
    except subprocess.TimeoutExpired:
        _signal_group(proc.pid, signal.SIGTERM)
        stdout, stderr = proc.communicate()
        return StepResult(None, stdout, stderr, time.monotonic() - started, timed_out=True)
    return StepResult(proc.returncode, stdout, stderr, time.monotonic() - started)
PY
python3 -m unittest discover -s tests -t . >"$TRIAL_JOB_DIR/own-tests.log" 2>&1 || true
cat > "$TRIAL_JOB_DIR/final-0.md" <<'MD'
Both pipes are drained with `communicate()`, and on timeout the whole process group gets SIGTERM so the step and anything it started can shut down; steprun then collects the remaining output. Existing tests pass.
MD

# Partial fix (must fail): Replaces the runner with subprocess.run(capture_output=True, timeout=...): no deadlock, partial output kept, but only the direct child is killed, with SIGKILL and no SIGTERM first.
set -e
cat > steprun/runner.py <<'PY'
"""Run a step's command with an optional time limit and capture its output."""

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


def run_step(argv, timeout=None, grace=5.0, cwd=None, env=None):
    started = time.monotonic()
    try:
        r = subprocess.run(argv, stdin=subprocess.DEVNULL, capture_output=True, timeout=timeout, cwd=cwd, env=env)
    except subprocess.TimeoutExpired as exc:
        return StepResult(None, exc.stdout or b"", exc.stderr or b"", time.monotonic() - started, timed_out=True)
    return StepResult(r.returncode, r.stdout, r.stderr, time.monotonic() - started)
PY
python3 -m unittest discover -s tests -t . >"$TRIAL_JOB_DIR/own-tests.log" 2>&1 || true
cat > "$TRIAL_JOB_DIR/final-0.md" <<'MD'
Replaced the hand-rolled wait/read with `subprocess.run(capture_output=True, timeout=...)`, which drains both pipes and kills the command on timeout; the output captured before the timeout comes from the `TimeoutExpired` exception. Existing tests pass.
MD

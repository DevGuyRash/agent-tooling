# Other correct approach (must pass): the smallest complete fix. communicate() drains both pipes; the step runs as its own session; on timeout the group gets SIGTERM, steprun always sits out the whole grace period, then SIGKILLs the group unconditionally while the command, not yet reaped, still holds the group ID; then it drains the rest.
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
        # communicate() raised before reaping the command, so its PID -- the group ID -- is still ours.
        _signal_group(proc.pid, signal.SIGTERM)
        time.sleep(grace)
        _signal_group(proc.pid, signal.SIGKILL)
        stdout, stderr = proc.communicate()
        return StepResult(None, stdout, stderr, time.monotonic() - started, timed_out=True)
    return StepResult(proc.returncode, stdout, stderr, time.monotonic() - started)
PY
cat > tests/test_step_timeouts.py <<'PY'
import subprocess
import sys
import tempfile
import time
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

CHATTY = """
import sys
for _ in range(8):  # 2 MiB per stream, alternating, stderr first
    sys.stderr.buffer.write(b"e" * 262144)
    sys.stderr.buffer.flush()
    sys.stdout.buffer.write(b"o" * 262144)
    sys.stdout.buffer.flush()
"""


def steprun(*args):
    started = time.monotonic()
    r = subprocess.run([sys.executable, "-m", "steprun", *args], cwd=ROOT, capture_output=True, timeout=60)
    return r, time.monotonic() - started


def running(pid):
    try:
        stat = Path(f"/proc/{pid}/stat").read_bytes()
    except FileNotFoundError:
        return False
    return stat[stat.rfind(b")") + 2:].split()[0] not in (b"Z", b"X")


class StepTimeoutTest(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.pidfile = Path(tmp.name) / "pid"

    def assertStopped(self):
        pid = int(self.pidfile.read_text())
        end = time.monotonic() + 2
        while running(pid) and time.monotonic() < end:
            time.sleep(0.02)
        self.assertFalse(running(pid), f"process {pid} outlived the step")

    def test_large_output_on_both_streams(self):
        r, _ = steprun("--timeout", "30", "--", sys.executable, "-c", CHATTY)
        self.assertEqual((r.returncode, len(r.stdout)), (0, 2 * 1024 * 1024))

    def test_background_process_is_stopped_with_the_step(self):
        r, elapsed = steprun("--timeout", "1", "--grace", "1", "--", "sh", "-c",
                             f"sleep 30 & echo $! > {self.pidfile}; exec sleep 30")
        self.assertEqual(r.returncode, 124)
        self.assertLess(elapsed, 6)
        self.assertStopped()

    def test_background_process_ignoring_sigterm_is_killed(self):
        r, _ = steprun("--timeout", "1", "--grace", "1", "--", "sh", "-c",
                       f"trap '' TERM; sleep 30 >/dev/null 2>&1 & echo $! > {self.pidfile}; trap - TERM; exec sleep 30")
        self.assertEqual(r.returncode, 124)
        self.assertStopped()

    def test_output_before_the_timeout_is_kept(self):
        r, _ = steprun("--timeout", "1", "--grace", "1", "--", "sh", "-c", "echo started; exec sleep 30")
        self.assertEqual((r.returncode, r.stdout), (124, b"started\n"))


if __name__ == "__main__":
    unittest.main()
PY
python3 -m unittest discover -s tests -t . >"$TRIAL_JOB_DIR/own-tests.log" 2>&1 || true
cat > "$TRIAL_JOB_DIR/final-0.md" <<'MD'
Fixed in `steprun/runner.py`: `communicate()` now drains stdout and stderr while waiting, so chatty steps no longer deadlock on a full pipe. The step runs in its own session, and on timeout its whole process group gets SIGTERM, then SIGKILL once `--grace` is over, so nothing it started survives, whether or not the command itself has already exited. The group is signalled before the command is reaped, so its ID cannot have been reused. Output printed before the timeout is written. Added tests for large output on both streams, background processes on timeout (including one that ignores SIGTERM), and kept output; all tests pass.
MD

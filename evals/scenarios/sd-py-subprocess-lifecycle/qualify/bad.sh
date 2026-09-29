# Plausible fix that misses the hazard (must fail): the pattern from the subprocess documentation.
# communicate() drains both pipes while waiting, which cures the hang on chatty steps, and on timeout
# the command gets SIGTERM, a wait of --grace, SIGKILL, then communicate() again to collect its output.
# Every signal goes to the direct child only: what the command started keeps running, and a background
# process that holds the pipes makes that last communicate() wait for it.
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
    """Run argv, wait up to `timeout` seconds for it, and return what it wrote.

    A step still running after `timeout` seconds is stopped: it gets SIGTERM,
    and SIGKILL if it is still running `grace` seconds later.
    """
    started = time.monotonic()
    proc = subprocess.Popen(
        argv,
        stdin=subprocess.DEVNULL,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        cwd=cwd,
        env=env,
    )
    try:
        # communicate() reads both pipes while it waits, so a step that writes more
        # than a pipe holds can never block on us.
        stdout, stderr = proc.communicate(timeout=timeout)
    except subprocess.TimeoutExpired:
        proc.terminate()
        try:
            proc.wait(timeout=grace)
        except subprocess.TimeoutExpired:
            proc.kill()
        stdout, stderr = proc.communicate()  # what it wrote before it was stopped
        return StepResult(None, stdout, stderr, time.monotonic() - started, timed_out=True)
    return StepResult(proc.returncode, stdout, stderr, time.monotonic() - started)
PY
cat > tests/test_large_output_and_timeouts.py <<'PY'
import subprocess
import sys
import time
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
MIB = 1024 * 1024

# 2 MiB on each stream, alternating, stderr first.
CHATTY = """
import sys
chunk = 256 * 1024
for _ in range(8):
    sys.stderr.buffer.write(b"e" * chunk)
    sys.stderr.buffer.flush()
    sys.stdout.buffer.write(b"o" * chunk)
    sys.stdout.buffer.flush()
sys.exit(int(sys.argv[1]))
"""


def steprun(*args):
    started = time.monotonic()
    r = subprocess.run([sys.executable, "-m", "steprun", *args], cwd=ROOT, capture_output=True, timeout=60)
    return r, time.monotonic() - started


class LargeOutputTest(unittest.TestCase):
    def test_more_than_a_pipe_holds_on_both_streams(self):
        r, elapsed = steprun("--timeout", "30", "--", sys.executable, "-c", CHATTY, "0")
        self.assertEqual(r.returncode, 0)
        self.assertEqual(r.stdout, b"o" * (2 * MIB))
        self.assertTrue(r.stderr.startswith(b"e" * (2 * MIB)))
        self.assertLess(elapsed, 20)

    def test_large_output_with_a_failing_status(self):
        r, _ = steprun("--timeout", "30", "--", sys.executable, "-c", CHATTY, "3")
        self.assertEqual(r.returncode, 3)
        self.assertEqual(len(r.stdout), 2 * MIB)


class TimeoutTest(unittest.TestCase):
    def test_command_ignoring_sigterm_is_killed_after_the_grace_period(self):
        r, elapsed = steprun("--timeout", "1", "--grace", "1", "--", "sh", "-c", "trap '' TERM; exec sleep 30")
        self.assertEqual(r.returncode, 124)
        self.assertGreaterEqual(elapsed, 2)
        self.assertLess(elapsed, 6)

    def test_output_written_before_the_timeout_is_kept(self):
        r, _ = steprun("--timeout", "1", "--grace", "1", "--", "sh", "-c",
                       "printf 'so %s\\n' far; printf 'so %s\\n' bad >&2; exec sleep 30")
        self.assertEqual(r.returncode, 124)
        self.assertEqual(r.stdout, b"so far\n")
        self.assertTrue(r.stderr.startswith(b"so bad\n"))


if __name__ == "__main__":
    unittest.main()
PY
python3 - <<'PY'
from pathlib import Path
p = Path("CHANGELOG.md")
p.write_text(p.read_text().replace("# Changelog\n\n", """# Changelog

## 1.3.1

- Steps that write a lot of output no longer hang.
- A step that times out is waited for, and killed if it outlives `--grace`; its output is written.

""", 1))
PY
python3 -m unittest discover -s tests -t . >"$TRIAL_JOB_DIR/own-tests.log" 2>&1 || true
cat > "$TRIAL_JOB_DIR/final-0.md" <<'MD'
Fixed both problems in `steprun/runner.py`.

- **Hang on chatty steps:** steprun called `wait()` before reading any output, so a step that wrote more than a pipe holds (64 KiB) blocked on the full pipe and never exited. It now uses `communicate()`, which drains stdout and stderr while it waits.
- **Timeouts:** steprun sent SIGTERM and returned at once without waiting, so the step kept running and its output was thrown away. It now waits up to `--grace` for the step to exit, sends SIGKILL if it has not, and then collects and writes what the step printed before the timeout.

Added tests for 2 MiB on both streams (success and failure), a command that ignores SIGTERM, and output kept on timeout. All tests pass.
MD

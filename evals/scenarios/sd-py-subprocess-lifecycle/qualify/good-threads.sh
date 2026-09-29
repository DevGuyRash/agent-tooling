# Other correct approach (must pass), with a different policy: reader threads drain both pipes; the command is waited for without being reaped; whenever the step ends (success, failure, or timeout) whatever is left in its process group gets SIGTERM, then SIGKILL after the grace period if any of it is still running; the command is reaped last.
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


POLL = 0.02
AFTER_KILL = 2.0


def _exited(pid):
    return os.waitid(os.P_PID, pid, os.WEXITED | os.WNOHANG | os.WNOWAIT) is not None


def _drain(pipe, chunks):
    with pipe:
        for data in iter(lambda: pipe.read1(65536), b""):
            chunks.append(data)


def run_step(argv, timeout=None, grace=5.0, cwd=None, env=None):
    started = time.monotonic()
    deadline = None if timeout is None else started + timeout
    proc = _popen(argv, cwd, env, start_new_session=True)
    out, err = [], []
    readers = [threading.Thread(target=_drain, args=(proc.stdout, out), daemon=True),
               threading.Thread(target=_drain, args=(proc.stderr, err), daemon=True)]
    for t in readers:
        t.start()
    timed_out = False
    try:
        while not _exited(proc.pid):
            if deadline is not None and time.monotonic() >= deadline:
                timed_out = True
                break
            time.sleep(POLL)
    finally:
        # The step ends with its command: whatever is left in its group is stopped, and the
        # command is reaped only afterwards, so the group ID cannot have been reused.
        _stop_group(proc.pid, grace)
        end = time.monotonic() + AFTER_KILL
        for t in readers:
            t.join(max(0.0, end - time.monotonic()))
        returncode = proc.wait()
    return StepResult(None if timed_out else returncode, b"".join(out), b"".join(err),
                      time.monotonic() - started, timed_out=timed_out)
PY
cat > tests/test_step_lifecycle.py <<'PY'
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
sys.exit(5)
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


class StepLifecycleTest(unittest.TestCase):
    """When a step ends, for whatever reason, nothing it started is left running."""

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
        self.assertEqual((r.returncode, len(r.stdout)), (5, 2 * 1024 * 1024))
        self.assertTrue(r.stderr.startswith(b"e" * (2 * 1024 * 1024) + b"steprun: "))

    def test_timeout_kills_a_child_that_ignores_sigterm_after_closing_its_output(self):
        r, elapsed = steprun("--timeout", "1", "--grace", "1", "--", "sh", "-c",
                             f"trap '' TERM; sleep 30 >/dev/null 2>&1 & echo $! > {self.pidfile}; trap - TERM; exec sleep 30")
        self.assertEqual(r.returncode, 124)
        self.assertLess(elapsed, 6)
        self.assertStopped()

    def test_step_ends_with_its_command_even_if_a_child_holds_the_output(self):
        r, elapsed = steprun("--timeout", "20", "--grace", "1", "--", "sh", "-c",
                             f"sleep 30 & echo $! > {self.pidfile}; echo done; exit 3")
        self.assertEqual((r.returncode, r.stdout), (3, b"done\n"))
        self.assertLess(elapsed, 5)
        self.assertStopped()

    def test_detached_leftovers_of_a_successful_step_are_stopped(self):
        r, _ = steprun("--", "sh", "-c", f"sleep 30 >/dev/null 2>&1 & echo $! > {self.pidfile}")
        self.assertEqual(r.returncode, 0)
        self.assertStopped()


if __name__ == "__main__":
    unittest.main()
PY
python3 -m unittest discover -s tests -t . >"$TRIAL_JOB_DIR/own-tests.log" 2>&1 || true
cat > "$TRIAL_JOB_DIR/final-0.md" <<'MD'
steprun now drains both pipes in reader threads, so large output on either stream can't block the step. The command runs in its own session, and whenever a step ends, whether it succeeds, fails, or times out, anything left in its process group gets SIGTERM and then SIGKILL after `--grace` if it is still running. The command is reaped only afterwards, so the group ID stays valid. A step that leaves a helper holding its output therefore finishes with its own exit status instead of hanging. Output printed before a timeout is written. Tests cover large output on both streams, a SIGTERM-ignoring child on timeout, and leftovers of successful and failing steps; all pass.
MD

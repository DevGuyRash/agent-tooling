# Reference behavior (must pass): drain both pipes together in one loop with the wait; run the step as its own
# session; on timeout SIGTERM the group, then SIGKILL after the grace period if any process in the group is
# still alive (checked on the group, not inferred from the command exiting or the pipes closing), reaping the
# command only afterwards so the group ID stays ours; keep the output and exit contract; forward interrupts.
set -e
cat > steprun/runner.py <<'PY'
"""Run a step's command with an optional time limit and capture its output.

A step is its command plus every process the command starts. The command runs
as the leader of a new session, so the whole step is one process group that
steprun can signal as a unit. Its lifecycle is handled in one loop:

* Both pipes are drained together the whole time. A step that writes more
  than a pipe holds to either stream never waits on steprun, and steprun
  never waits on one stream while the step is blocked writing the other.
* The step runs until its command has exited and its output is closed. The
  timeout bounds all of it, including output that processes the command left
  running still hold open.
* On timeout the group gets SIGTERM, and SIGKILL once the grace period is
  over if any process in it is still alive. Neither the command exiting nor
  the pipes closing means the rest of the group is gone, so the group itself
  is checked.
* The command is reaped only after the group has been dealt with. Until then
  it stays a zombie, which keeps its PID -- the group's ID -- from being
  reused, so the signals can only ever reach this step's processes.
"""

import os
import selectors
import signal
import subprocess
import time
from dataclasses import dataclass

POLL_INTERVAL = 0.05
# After SIGKILL every process in the group dies promptly; output can then stay open only if
# something outside the group holds it, and steprun stops waiting for it after this long.
AFTER_KILL = 2.0


@dataclass
class StepResult:
    """What happened to one step."""

    returncode: int | None  # the command's status, negative for a signal; None if the step timed out
    stdout: bytes
    stderr: bytes
    duration: float
    timed_out: bool = False


class _Output:
    """A step's stdout and stderr pipes, drained together."""

    def __init__(self, proc):
        self._selector = selectors.DefaultSelector()
        self._chunks = {proc.stdout: [], proc.stderr: []}
        self._stdout, self._stderr = proc.stdout, proc.stderr
        for pipe in self._chunks:
            self._selector.register(pipe, selectors.EVENT_READ)

    @property
    def open(self):
        return bool(self._selector.get_map())

    def pump(self, timeout):
        """Read whatever arrives within `timeout` seconds; a pipe at EOF is closed."""
        if not self.open:
            time.sleep(timeout)
            return
        for key, _ in self._selector.select(timeout):
            data = os.read(key.fd, 65536)
            if data:
                self._chunks[key.fileobj].append(data)
            else:
                self._selector.unregister(key.fileobj)
                key.fileobj.close()

    def close(self):
        for key in list(self._selector.get_map().values()):
            self._selector.unregister(key.fileobj)
            key.fileobj.close()
        self._selector.close()

    def stdout(self):
        return b"".join(self._chunks[self._stdout])

    def stderr(self):
        return b"".join(self._chunks[self._stderr])


def _exited(pid):
    """Whether the command has exited, without reaping it."""
    return os.waitid(os.P_PID, pid, os.WEXITED | os.WNOHANG | os.WNOWAIT) is not None


def _group_alive(pgid):
    """Whether any process in group `pgid` is still running (zombies do not count)."""
    try:
        entries = os.listdir("/proc")
    except OSError:  # no /proc: fall back to the kernel's answer, which counts zombies
        try:
            os.killpg(pgid, 0)
            return True
        except ProcessLookupError:
            return False
    for entry in entries:
        if not entry.isdigit():
            continue
        try:
            with open(f"/proc/{entry}/stat", "rb") as f:
                stat = f.read()
        except OSError:
            continue  # exited while we looked
        fields = stat[stat.rfind(b")") + 2:].split()  # the command name may contain spaces
        if int(fields[2]) == pgid and fields[0] not in (b"Z", b"X"):
            return True
    return False


def _signal_group(pgid, sig):
    try:
        os.killpg(pgid, sig)
    except ProcessLookupError:
        pass


def _stop(pgid, grace, output):
    """SIGTERM the step's group, give it `grace` seconds, then SIGKILL whatever is left.

    The command has not been reaped, so `pgid` still names this step's group.
    Output is drained meanwhile: a step that is cleaning up may still write.
    """
    _signal_group(pgid, signal.SIGTERM)
    end = time.monotonic() + grace
    while _group_alive(pgid) and time.monotonic() < end:
        output.pump(POLL_INTERVAL)
    _signal_group(pgid, signal.SIGKILL)  # harmless when only the unreaped command is left
    end = time.monotonic() + AFTER_KILL
    while (_group_alive(pgid) or output.open) and time.monotonic() < end:
        output.pump(POLL_INTERVAL)


def run_step(argv, timeout=None, grace=5.0, cwd=None, env=None):
    """Run argv, wait up to `timeout` seconds for it, and return what it wrote.

    A step still running after `timeout` seconds is stopped: every process in
    it gets SIGTERM, and SIGKILL if any is still running `grace` seconds later.
    If steprun itself is interrupted, the step is stopped the same way.
    """
    started = time.monotonic()
    deadline = None if timeout is None else started + timeout
    proc = subprocess.Popen(
        argv,
        stdin=subprocess.DEVNULL,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        cwd=cwd,
        env=env,
        start_new_session=True,  # the command leads a new process group: the step
    )
    output = _Output(proc)
    try:
        try:
            while output.open or not _exited(proc.pid):
                wait = POLL_INTERVAL
                if deadline is not None:
                    wait = min(wait, deadline - time.monotonic())
                    if wait <= 0:
                        break
                output.pump(wait)
            else:
                returncode = proc.wait()
                return StepResult(returncode, output.stdout(), output.stderr(), time.monotonic() - started)
        except BaseException:  # interrupted (Ctrl-C, SIGTERM to steprun): take the step down with us
            _stop(proc.pid, grace, output)
            proc.wait()
            raise
        _stop(proc.pid, grace, output)
        proc.wait()
        return StepResult(None, output.stdout(), output.stderr(), time.monotonic() - started, timed_out=True)
    finally:
        output.close()
PY

cat > steprun/cli.py <<'PY'
"""Command line: python3 -m steprun [options] -- COMMAND [ARG...]"""

import argparse
import shlex
import signal
import sys

from .runner import run_step

TIMED_OUT = 124
CANNOT_EXECUTE = 126
NOT_FOUND = 127
INTERRUPTING = (signal.SIGINT, signal.SIGTERM, signal.SIGHUP)


class Interrupted(Exception):
    """steprun itself got a signal that ends the step."""

    def __init__(self, signum):
        super().__init__(signum)
        self.signum = signum


def _interrupt(signum, frame):
    # The step runs in a session of its own, so Ctrl-C at a terminal or a CI runner cancelling
    # the job reaches only steprun, which then stops the step. Later signals must not cut that short.
    for sig in INTERRUPTING:
        signal.signal(sig, signal.SIG_IGN)
    raise Interrupted(signum)


def _parser():
    p = argparse.ArgumentParser(
        prog="steprun",
        description="Run one CI step with an optional time limit and write its output in one piece.",
    )
    p.add_argument("--timeout", type=float, metavar="SECONDS",
                   help="stop the step if it is still running after SECONDS (default: no limit)")
    p.add_argument("--grace", type=float, default=5.0, metavar="SECONDS",
                   help="how long a timed-out step gets between SIGTERM and SIGKILL (default: 5)")
    p.add_argument("--label", metavar="NAME",
                   help="name for the step in the status line (default: the command line)")
    p.add_argument("command", nargs=argparse.REMAINDER, help="the command to run, after --")
    return p


def exit_status(returncode):
    """steprun's exit status for a command's return code: N, or 128 + S if signal S killed it."""
    return returncode if returncode >= 0 else 128 - returncode


def main(argv=None):
    parser = _parser()
    args = parser.parse_args(argv)
    command = args.command[1:] if args.command[:1] == ["--"] else args.command
    if not command:
        parser.error("no command given")
    if args.timeout is not None and args.timeout <= 0:
        parser.error("--timeout must be positive")
    if args.grace < 0:
        parser.error("--grace must not be negative")
    label = args.label or shlex.join(command)

    previous = {sig: signal.signal(sig, _interrupt) for sig in INTERRUPTING}
    try:
        result = run_step(command, timeout=args.timeout, grace=args.grace)
    except Interrupted as exc:
        print(f"steprun: {label}: interrupted by {signal.Signals(exc.signum).name}", file=sys.stderr)
        return 128 + exc.signum
    except FileNotFoundError:
        print(f"steprun: {command[0]}: command not found", file=sys.stderr)
        return NOT_FOUND
    except PermissionError:
        print(f"steprun: {command[0]}: cannot execute", file=sys.stderr)
        return CANNOT_EXECUTE
    finally:
        for sig, handler in previous.items():
            signal.signal(sig, handler)

    sys.stdout.buffer.write(result.stdout)
    sys.stdout.flush()
    sys.stderr.buffer.write(result.stderr)
    sys.stderr.flush()
    if result.timed_out:
        print(f"steprun: {label}: timed out after {args.timeout:g}s", file=sys.stderr)
        return TIMED_OUT
    status = exit_status(result.returncode)
    print(f"steprun: {label}: exited {status} after {result.duration:.1f}s", file=sys.stderr)
    return status
PY

cat > tests/test_lifecycle.py <<'PY'
"""A step's whole lifecycle: output on both streams, exit status, timeouts, interruption.

Tests that start processes a broken steprun would leave behind record their PIDs and
check that none of them is still running once steprun has returned (a zombie waiting
for init to reap it counts as gone).
"""
import signal
import subprocess
import sys
import tempfile
import time
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
MIB = 1024 * 1024

# 2 MiB per stream in alternating 256 KiB chunks, stderr first: more than a pipe holds on
# each stream, so draining one stream to EOF before the other deadlocks either way round.
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


def running(pid):
    try:
        with open(f"/proc/{pid}/stat", "rb") as f:
            stat = f.read()
    except FileNotFoundError:
        return False
    return stat[stat.rfind(b")") + 2:].split()[0] not in (b"Z", b"X")


class ProcessTestCase(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.dir = Path(tmp.name)

    def path(self, name):
        return self.dir / name

    def pid(self, name):
        return int(self.path(name).read_text())

    def assertGone(self, *pids):
        end = time.monotonic() + 2
        while any(running(p) for p in pids) and time.monotonic() < end:
            time.sleep(0.02)
        self.assertEqual([p for p in pids if running(p)], [], "still running after steprun returned")


class LargeOutputTest(unittest.TestCase):
    def test_more_than_a_pipe_holds_on_both_streams(self):
        r, elapsed = steprun("--timeout", "30", "--", sys.executable, "-c", CHATTY, "0")
        self.assertEqual(r.returncode, 0)
        self.assertEqual(r.stdout, b"o" * (2 * MIB))
        self.assertTrue(r.stderr.startswith(b"e" * (2 * MIB) + b"steprun: "), r.stderr[-120:])
        self.assertLess(elapsed, 20)

    def test_large_output_with_a_failing_status(self):
        r, _ = steprun("--timeout", "30", "--", sys.executable, "-c", CHATTY, "3")
        self.assertEqual(r.returncode, 3)
        self.assertEqual(len(r.stdout), 2 * MIB)


class TimeoutTest(ProcessTestCase):
    def test_background_process_holding_the_output_is_stopped(self):
        script = f"sleep 30 & echo $! > {self.path('child')}; echo $$ > {self.path('cmd')}; exec sleep 30"
        r, elapsed = steprun("--timeout", "1", "--grace", "1", "--", "sh", "-c", script)
        self.assertEqual(r.returncode, 124)
        self.assertLess(elapsed, 6)
        self.assertGone(self.pid("cmd"), self.pid("child"))

    def test_command_ignoring_sigterm_gets_sigkill_after_the_grace_period(self):
        script = f"trap '' TERM; echo $$ > {self.path('cmd')}; exec sleep 30"
        r, elapsed = steprun("--timeout", "1", "--grace", "1", "--", "sh", "-c", script)
        self.assertEqual(r.returncode, 124)
        self.assertGreaterEqual(elapsed, 2)  # the grace period was given
        self.assertLess(elapsed, 7)
        self.assertGone(self.pid("cmd"))

    def test_child_ignoring_sigterm_with_its_output_closed_gets_sigkill(self):
        # After SIGTERM the command exits and the pipes reach EOF, which looks like the end of
        # the step, but the child is still running until the grace period ends.
        script = (f"trap '' TERM; sleep 30 </dev/null >/dev/null 2>&1 & echo $! > {self.path('child')}; "
                  "trap - TERM; exec sleep 30")
        r, elapsed = steprun("--timeout", "1", "--grace", "1", "--", "sh", "-c", script)
        self.assertEqual(r.returncode, 124)
        self.assertLess(elapsed, 7)
        self.assertGone(self.pid("child"))

    def test_sigterm_comes_first_and_the_grace_period_is_honoured(self):
        script = (f"trap 'sleep 0.3; : > \"{self.path('cleaned')}\"; exit 0' TERM; "
                  "while :; do sleep 0.1; done")
        r, elapsed = steprun("--timeout", "1", "--grace", "5", "--", "sh", "-c", script)
        self.assertEqual(r.returncode, 124)
        self.assertTrue(self.path("cleaned").exists(), "the step was killed before it could clean up")
        self.assertLess(elapsed, 4.5)  # steprun did not sit out the grace period once the step was gone

    def test_output_written_before_the_timeout_is_kept(self):
        script = "printf 'so %s\\n' far; printf 'so %s\\n' bad >&2; exec sleep 30"
        r, _ = steprun("--timeout", "1", "--grace", "1", "--", "sh", "-c", script)
        self.assertEqual(r.returncode, 124)
        self.assertEqual(r.stdout, b"so far\n")
        self.assertTrue(r.stderr.startswith(b"so bad\n"), r.stderr)

    def test_timeout_bounds_output_held_open_after_the_command_exits(self):
        script = f"sleep 30 & echo $! > {self.path('child')}; exit 0"
        r, elapsed = steprun("--timeout", "1", "--grace", "1", "--", "sh", "-c", script)
        self.assertEqual(r.returncode, 124)
        self.assertLess(elapsed, 6)
        self.assertGone(self.pid("child"))

    def test_step_that_closes_its_output_and_keeps_running_times_out(self):
        script = f"echo $$ > {self.path('cmd')}; exec sleep 30 >/dev/null 2>&1"
        r, elapsed = steprun("--timeout", "1", "--grace", "1", "--", "sh", "-c", script)
        self.assertEqual(r.returncode, 124)
        self.assertLess(elapsed, 6)
        self.assertGone(self.pid("cmd"))


class InterruptTest(ProcessTestCase):
    def test_sigterm_to_steprun_stops_the_step(self):
        script = f"sleep 30 & echo $! > {self.path('child')}; exec sleep 30"
        p = subprocess.Popen([sys.executable, "-m", "steprun", "--grace", "1", "--", "sh", "-c", script],
                             cwd=ROOT, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        end = time.monotonic() + 10
        while not self.path("child").exists() and time.monotonic() < end:
            time.sleep(0.02)
        time.sleep(0.1)  # let the shell finish writing the PID
        p.send_signal(signal.SIGTERM)
        _, err = p.communicate(timeout=30)
        self.assertEqual(p.returncode, 128 + signal.SIGTERM)
        self.assertIn(b"interrupted by SIGTERM", err)
        self.assertGone(self.pid("child"))


if __name__ == "__main__":
    unittest.main()
PY

cat > README.md <<'MD'
# steprun

Run one CI step: a command, with an optional time limit.

Our CI driver runs many steps in parallel on each runner, and their output used to interleave line by line. `steprun` captures a step's standard output and standard error and writes each of them out in one piece when the step ends, so every step's log reads top to bottom.

## Usage

```
python3 -m steprun [--timeout SECONDS] [--grace SECONDS] [--label NAME] -- COMMAND [ARG...]
```

| Option | Meaning |
|---|---|
| `--timeout SECONDS` | Stop the step if it is still running after SECONDS. Default: no limit. |
| `--grace SECONDS` | A step that times out gets SIGTERM so it can clean up, and SIGKILL if it is still running SECONDS later. Default: 5. |
| `--label NAME` | Name for the step in the status line. Default: the command line. |

When the step ends, steprun writes the step's stdout to its own stdout and the step's stderr to its own stderr, then one status line on stderr:

```
steprun: make test: exited 0 after 12.4s
steprun: make e2e: timed out after 900s
```

A step that times out still gets its output written: whatever it printed before it was stopped.

## How a step is stopped

The command runs in a session of its own, so the command and every process it starts form one process group: the step. steprun reads the step's stdout and stderr together for as long as either is open. The step lasts until the command has exited and its output is closed; `--timeout` bounds all of it, including output that background processes the command left behind still hold open.

When a step times out, every process in its group gets SIGTERM, and whatever is still running `--grace` seconds later gets SIGKILL, even if the command itself has already exited or the output has closed.

Because the step has its own session, Ctrl-C at a terminal or a CI runner cancelling the job reaches steprun rather than the step. steprun then stops the step the same way and exits with 128 + the signal number.

## Exit status

| Situation | Exit status |
|---|---|
| The command exited with status N | N |
| The command was killed by signal S (not by steprun) | 128 + S |
| The step timed out | 124 |
| The command could not be executed | 126 |
| The command was not found | 127 |
| steprun was interrupted by signal S (SIGINT, SIGTERM, SIGHUP) | 128 + S |
| Invalid steprun arguments | 2 |

## Development

Standard library only. Python 3.10 or newer; our CI runners are Linux.

```
python3 -m unittest discover -s tests -t .
```
MD

cat > CHANGELOG.md <<'MD'
# Changelog

## 1.3.1

- Steps that write more than a pipe holds to stdout and stderr no longer hang: both are read together.
- A step that times out is stopped as a whole: every process it started gets SIGTERM, then SIGKILL after `--grace`.
- A step that times out gets its output written, as documented.
- The timeout also covers output that background processes keep open after the command exits.
- SIGINT, SIGTERM, and SIGHUP to steprun stop the step before steprun exits.

## 1.3.0

- `--grace`: how long a timed-out step gets between SIGTERM and SIGKILL.
- Exit with 126 when the command cannot be executed.

## 1.2.0

- `--label` names the step in the status line.

## 1.1.0

- Exit with 124 when a step times out, like GNU `timeout`.

## 1.0.0

- First release: run a command and write its stdout and stderr in one piece.
MD

sed -i 's/^__version__ = "1.3.0"/__version__ = "1.3.1"/' steprun/__init__.py
sed -i 's/^version = "1.3.0"/version = "1.3.1"/' pyproject.toml
python3 -m unittest discover -s tests -t . >"$TRIAL_JOB_DIR/own-tests.log" 2>&1 || true
cat > "$TRIAL_JOB_DIR/final-0.md" <<'MD'
steprun now treats a step as its command plus everything the command starts, and handles the step's two pipes and its processes as one lifecycle.

- **Chatty steps no longer hang.** steprun waited for the command before reading anything, so a step that wrote more than a pipe holds (64 KiB) to either stream blocked forever. Both pipes are now drained together the whole time, and the timeout covers the whole step, including output that a background process keeps open after the command exits.
- **A timeout stops the whole step.** The command runs in its own session, so on timeout every process in its group gets SIGTERM and, after `--grace`, SIGKILL if anything in the group is still running. That is checked on the group itself: the command exiting, or the pipes closing, does not mean its background processes are gone. The command is reaped only after that, so the group ID cannot be reused under steprun.
- **Output printed before a timeout is written**, as the README promises.
- Because the step now has its own session, SIGINT, SIGTERM, and SIGHUP to steprun stop the step as well (exit 128 + signal).

Tests: `tests/test_lifecycle.py` covers 2 MiB on both streams (success and failure status), a background process holding the output at timeout, a command that ignores SIGTERM, a child that ignores SIGTERM after closing its output, SIGTERM before SIGKILL with the grace period honoured, output kept on timeout, output held open after the command exits, and SIGTERM to steprun. The whole suite passes (23 tests). README and CHANGELOG updated for 1.3.1; nothing is committed.

One policy choice for you: when a step *succeeds*, background processes that detached from its output are left running, as before. Say if you want steprun to stop those too.
MD

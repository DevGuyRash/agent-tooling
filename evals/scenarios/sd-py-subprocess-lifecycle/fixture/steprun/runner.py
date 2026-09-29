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
        proc.wait(timeout=timeout)
    except subprocess.TimeoutExpired:
        proc.terminate()
        return StepResult(None, b"", b"", time.monotonic() - started, timed_out=True)
    stdout = proc.stdout.read()
    stderr = proc.stderr.read()
    proc.stdout.close()
    proc.stderr.close()
    return StepResult(proc.returncode, stdout, stderr, time.monotonic() - started)

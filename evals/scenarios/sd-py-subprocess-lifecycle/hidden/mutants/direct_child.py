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


def _signal_group(pgid, sig):
    try:
        os.killpg(pgid, sig)
    except ProcessLookupError:
        pass


def _group_alive(pgid):
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
    _signal_group(pgid, signal.SIGTERM)
    end = time.monotonic() + grace
    while _group_alive(pgid) and time.monotonic() < end:
        time.sleep(0.05)
    _signal_group(pgid, signal.SIGKILL)


def _popen(argv, cwd, env, **kw):
    return subprocess.Popen(argv, stdin=subprocess.DEVNULL, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                            cwd=cwd, env=env, **kw)

def run_step(argv, timeout=None, grace=5.0, cwd=None, env=None):
    started = time.monotonic()
    proc = _popen(argv, cwd, env)
    try:
        stdout, stderr = proc.communicate(timeout=timeout)
    except subprocess.TimeoutExpired:
        proc.terminate()
        try:
            proc.wait(timeout=grace)
        except subprocess.TimeoutExpired:
            proc.kill()
        stdout, stderr = proc.communicate()
        return StepResult(None, stdout, stderr, time.monotonic() - started, timed_out=True)
    return StepResult(proc.returncode, stdout, stderr, time.monotonic() - started)

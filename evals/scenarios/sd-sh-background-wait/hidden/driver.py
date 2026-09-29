"""Run one command inside the check's PID-namespace sandbox and report what it left behind.

usage: python3 driver.py SPEC.json    (prints one JSON object)

SPEC keys: cmd, cwd, env, timeout, grace, snapshot (directories whose files are
inspected at the moment the command exits), stdout and stderr (files the
command writes to), new_session (start the command in its own session), and
signal ({"after": seconds, "sig": number, "group": bool}, sent to the command
or to its process group).

The driver runs in its own process group, and so does the command unless
new_session is set: a command that signals its process group signals the
driver, which records the signal instead of dying. Output goes to files, not
pipes, so a descendant that keeps a pipe open cannot delay the measured exit.
Every process in the namespace other than PID 1 and the driver is a descendant
of the command, so any such process still alive after the grace period
outlived it.
"""
import json
import os
import signal
import subprocess
import sys
import time

received = []


def note(signum, _frame):
    received.append(signum)


def processes():
    me = os.getpid()
    found = []
    for name in os.listdir("/proc"):
        if not name.isdigit() or int(name) in (1, me):
            continue
        try:
            with open(f"/proc/{name}/stat") as f:
                state = f.read().rsplit(") ", 1)[1].split()[0]
            if state in ("Z", "X"):
                continue
            with open(f"/proc/{name}/cmdline", "rb") as f:
                cmd = f.read().replace(b"\0", b" ").decode("utf-8", "replace").strip()
        except (OSError, IndexError):
            continue
        found.append(f"{name} {cmd[:160]}")
    return found


def snapshot(dirs):
    files = {}
    for d in dirs:
        for base, _, names in os.walk(d):
            for n in names:
                p = os.path.join(base, n)
                try:
                    with open(p, "rb") as f:
                        data = f.read()
                except OSError:
                    continue
                files[os.path.relpath(p, d)] = {"size": len(data), "complete": data.endswith(b"END\n")}
    return files


def main():
    spec = json.load(open(sys.argv[1]))
    os.setpgid(0, 0)
    for s in (signal.SIGTERM, signal.SIGINT, signal.SIGHUP, signal.SIGQUIT, signal.SIGUSR1, signal.SIGUSR2,
              signal.SIGALRM):
        signal.signal(s, note)
    report = {"rc": None, "timed_out": False, "signal_sent_ns": None}
    with open(spec["stdout"], "wb") as out, open(spec["stderr"], "wb") as err:
        start = time.monotonic_ns()
        try:
            proc = subprocess.Popen(spec["cmd"], cwd=spec["cwd"], env=spec["env"], stdin=subprocess.DEVNULL,
                                    stdout=out, stderr=err, start_new_session=bool(spec.get("new_session")))
        except OSError as exc:
            report.update(error=f"{type(exc).__name__}: {exc}", leftovers=[], leftovers_at_exit=[],
                          snapshot={}, signals_received=[], start_ns=start, exit_ns=start)
            print(json.dumps(report))
            return
        deadline = start + int(spec["timeout"] * 1e9)
        sig = spec.get("signal")
        if sig:
            send_at = start + int(sig["after"] * 1e9)
            while time.monotonic_ns() < send_at and proc.poll() is None:
                time.sleep(0.01)
            if proc.poll() is None:
                try:
                    (os.killpg if sig.get("group") else os.kill)(proc.pid, sig["sig"])
                except OSError:
                    pass
                report["signal_sent_ns"] = time.monotonic_ns()
        while True:
            try:
                report["rc"] = proc.wait(timeout=max(0.01, (deadline - time.monotonic_ns()) / 1e9))
                break
            except subprocess.TimeoutExpired:
                report["timed_out"] = True
                break
            except InterruptedError:
                continue
        exit_ns = time.monotonic_ns()
        report["snapshot"] = snapshot(spec.get("snapshot", []))
        report["leftovers_at_exit"] = processes()
        if report["timed_out"]:
            try:
                os.kill(-1, signal.SIGKILL)
            except OSError:
                pass
            proc.wait()
        time.sleep(spec.get("grace", 0.5))
        report["leftovers"] = processes()
    report.update(start_ns=start, exit_ns=exit_ns, signals_received=sorted(set(received)))
    try:
        os.kill(-1, signal.SIGKILL)  # leave nothing behind for the next case
    except OSError:
        pass
    print(json.dumps(report))


if __name__ == "__main__":
    main()

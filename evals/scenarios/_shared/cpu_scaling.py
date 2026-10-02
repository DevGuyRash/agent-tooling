"""CPU-time scaling measurement for checks that run agent code and a reference on generated inputs at two sizes
(SMALL and LARGE) and decide whether the agent's code grows like the reference's.

This is the protocol perf-dedupe-ts/check.py and perf-dedupe-py/check.py carry inline (their qualify READMEs
give its calibration); checks written since import it from here. A check supplies a runner and two callbacks:

    runner(who, name, out_dir, budget, limit) -> dict   who is "ref" or "agent", name "small" or "large"
    complete(ref, agent) -> bool                        the agent's run did the whole job (exit 0, same output)
    incomplete(name, ref, agent) -> str                 why not, for the scaling note

The runner's dict carries at least rc (None when stopped at the wall-time limit), cpu, wall, err, and rss_mb;
Spawners.run gives all but rss_mb (it gives rss_kb) and err, which the runner reads from the file it named.

How CPU time is measured. User plus system time of every process and thread in the sandbox, read with wait4
by a small spawner process of this module's (starting programs from the lean spawner keeps the trial process's
memory out of the peak-memory measure). Inside the sandbox the command runs under a reaper, the namespace's
first process (bwrap --as-pid-1; see reaped()): when the command exits, the reaper kills and reaps every
process still there, so child processes nobody waited for are counted too, and given a CPU budget it stops the
whole sandbox once the processes in it have used more than that (summed over the sandbox's own /proc, seen on
two polls in a row) and exits OVER_BUDGET_RC.

How the decision is made. Rounds of (reference SMALL, agent SMALL, reference LARGE, agent LARGE), so the four
runs one round's growth compares are close together in time and load affects them alike, until `rounds`
rounds are done or a majority of them already decides the median growth. The agent's run is stopped as soon
as its CPU time passes cpu_factor times the reference run's just before it plus slack_s; the size fails when
that happens twice (the second time on an immediate repeat with a fresh reference run). A run is also stopped
after max(kill_factor times the reference's wall time, kill_floor_s), a backstop for code that waits rather
than computes. The agent's growth in CPU time from SMALL to LARGE, as a multiple of the reference's, must be
at most growth_factor (median over the rounds).
"""
import json
import queue
import shutil
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path

OVER_BUDGET_RC = 152  # the reaper's exit status when it stopped the sandbox at its CPU budget
HOST_PYTHON = "/usr/bin/python3" if Path("/usr/bin/python3").exists() else (shutil.which("python3") or sys.executable)
# The reaper runs inside the sandbox, where the home is hidden, so it needs a python3 outside it.
SANDBOX_PYTHON = next((p for p in ("/usr/bin/python3", "/usr/local/bin/python3") if Path(p).exists()), None)


@dataclass(frozen=True)
class Limits:
    cpu_factor: float = 10.0    # the agent's CPU time may be this many times the reference's ...
    slack_s: float = 1.0        # ... plus this, at each size
    growth_factor: float = 2.0  # the agent's CPU growth from SMALL to LARGE may be this many times the reference's
    rounds: int = 3             # rounds of (reference SMALL, agent SMALL, reference LARGE, agent LARGE)
    kill_factor: float = 20.0   # wall-time backstop for an agent run: this many times the reference's ...
    kill_floor_s: float = 60.0  # ... and at least this
    ref_limit_s: float = 600.0  # wall-time limit for a reference run


# A spawner starts each program and reads the kernel's accounting for it with wait4.
SPAWNER = r"""
import json, os, subprocess, sys, time
for line in sys.stdin:
    req = json.loads(line)
    with open(req["out"], "wb") as out, open(req["err"], "wb") as err:
        start = time.monotonic()
        proc = subprocess.Popen(req["argv"], env=req["env"], stdin=subprocess.DEVNULL, stdout=out, stderr=err)
        killed = False
        while True:
            pid, status, usage = os.wait4(proc.pid, os.WNOHANG)
            if pid:
                break
            if time.monotonic() - start > req["limit"]:
                proc.kill()
                pid, status, usage = os.wait4(proc.pid, 0)
                killed = True
                break
            time.sleep(0.02)
    proc.returncode = 0
    print(json.dumps({"rc": None if killed else os.waitstatus_to_exitcode(status),
                      "wall": time.monotonic() - start, "cpu": usage.ru_utime + usage.ru_stime,
                      "rss_kb": usage.ru_maxrss}), flush=True)
"""


# The reaper is the first process in the sandbox, run by python3 -I -S: REAPER BUDGET FSIZE ARGV... It starts
# the command with the file-size limit, waits for it, and then kills and reaps every process left in the
# sandbox, so the accounting that reaches the spawner through bwrap's exit includes them. Given a CPU budget
# (seconds; 0 for none), it also stops the whole sandbox once the processes in it have used more CPU time than
# that, and exits OVER_BUDGET_RC.
REAPER = r"""
import os, resource, signal, sys, time
budget, fsize, argv = float(sys.argv[1]), int(sys.argv[2]), sys.argv[3:]
TICK = os.sysconf("SC_CLK_TCK")

def used():
    total = 0
    for name in os.listdir("/proc"):
        if name.isdigit():
            try:
                with open("/proc/" + name + "/stat", "rb") as fh:
                    total += sum(map(int, fh.read().rsplit(b")", 1)[1].split()[11:15]))
            except (OSError, IndexError, ValueError):
                pass
    return total / TICK

child = os.fork()
if child == 0:
    try:
        for sig in (signal.SIGPIPE, signal.SIGXFSZ):
            signal.signal(sig, signal.SIG_DFL)
        resource.setrlimit(resource.RLIMIT_FSIZE, (fsize, fsize))
        os.execvp(argv[0], argv)
    except OSError as exc:
        os.write(2, ("%s: %s\n" % (argv[0], exc.strerror)).encode())
    os._exit(127)
signal.signal(signal.SIGINT, signal.SIG_IGN)
status, strikes = None, 0

def reap_ready():
    global status
    while True:
        try:
            pid, st = os.waitpid(-1, os.WNOHANG)
        except ChildProcessError:
            return
        if not pid:
            return
        if pid == child:
            status = st

while True:
    reap_ready()
    if status is not None:
        break
    if budget:
        strikes = strikes + 1 if used() > budget else 0
        if strikes == 2:
            break
    time.sleep(0.05)
try:
    os.kill(-1, signal.SIGKILL)
except ProcessLookupError:
    pass
while True:
    try:
        os.wait()
    except ChildProcessError:
        break
if status is None:
    os._exit(OVER_BUDGET_RC)
code = os.waitstatus_to_exitcode(status)
os._exit(code if code >= 0 else 128 - code)
""".replace("OVER_BUDGET_RC", str(OVER_BUDGET_RC))


def reaped(argv, budget=0.0, file_limit=1 << 30):
    """A no_interpreter.confined() argv made to run its command under the reaper as the namespace's first
    process, with this CPU budget in seconds (0 for none) and files capped at file_limit bytes. Append the
    command to the result."""
    if SANDBOX_PYTHON is None:
        raise RuntimeError("python3 is required at /usr/bin or /usr/local/bin for the check's sandbox")
    at = argv.index("--unshare-pid") + 1
    return (argv[:at] + ["--as-pid-1"] + argv[at:]
            + [SANDBOX_PYTHON, "-I", "-S", "-c", REAPER, f"{budget:.3f}", str(file_limit)])


class Spawners:
    """A pool of spawner processes; run() starts one program on a free one and returns its accounting."""

    def __init__(self, count):
        self._free = queue.Queue()
        self._all = []
        for _ in range(count):
            proc = subprocess.Popen([HOST_PYTHON, "-I", "-S", "-c", SPAWNER], stdin=subprocess.PIPE,
                                    stdout=subprocess.PIPE, text=True, env={"PATH": "/usr/bin:/bin"})
            self._all.append(proc)
            self._free.put(proc)

    def run(self, argv, env, out, err, limit):
        """{rc, wall, cpu, rss_kb} for argv with stdout to the file out and stderr to err; rc is None when
        the run was stopped after limit seconds of wall time."""
        proc = self._free.get()
        try:
            proc.stdin.write(json.dumps({"argv": argv, "env": env, "out": str(out), "err": str(err),
                                         "limit": limit}) + "\n")
            proc.stdin.flush()
            line = proc.stdout.readline()
        finally:
            self._free.put(proc)
        if not line:
            raise RuntimeError("the check's spawner stopped")
        return json.loads(line)

    def close(self):
        for proc in self._all:
            proc.stdin.close()
            try:
                proc.wait(timeout=10)
            except subprocess.TimeoutExpired:
                proc.kill()
                proc.wait()

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        self.close()


def tail(path, size=400):
    """The last `size` bytes of a file this check wrote, as text."""
    path = Path(path)
    with open(path, "rb") as fh:
        fh.seek(max(0, path.stat().st_size - size))
        return fh.read().decode("utf-8", "replace")


def median(values):
    values = sorted(values)
    mid = len(values) // 2
    return values[mid] if len(values) % 2 else (values[mid - 1] + values[mid]) / 2


def scaling(runner, base, complete, incomplete, limits=Limits()):
    """(whether the agent's code passes, measures) under the protocol above. base is a scratch directory of
    the check's; each run's files go in a directory under it."""

    def pair(name, out):
        ref = runner("ref", name, out / "ref", 0, limits.ref_limit_s)
        if ref["rc"] != 0:
            raise RuntimeError(f"the reference failed on the {name} input: {ref['err'][-200:]}")
        budget = limits.cpu_factor * ref["cpu"] + limits.slack_s
        limit = max(limits.kill_factor * ref["wall"], limits.kill_floor_s)
        agent = runner("agent", name, out / "agent", budget, limit)
        agent.update(budget=budget, limit=limit)
        return ref, agent

    def over(agent):
        return agent["rc"] is not None and (agent["rc"] == OVER_BUDGET_RC or agent["cpu"] > agent["budget"])

    def failure(name, ref, agent):
        if agent["rc"] is None:
            return f"{name}: stopped after {agent['limit']:.0f}s of wall time (the reference took {ref['wall']:.1f}s)"
        if over(agent):
            return f"{name}: over {agent['cpu']:.1f}s of CPU time against the reference's {ref['cpu']:.1f}s"
        if not complete(ref, agent):
            return incomplete(name, ref, agent)
        return None

    def growth(rnd, who=None):
        if who is None:
            return growth(rnd, 1) / growth(rnd, 0)
        return rnd["large"][who]["cpu"] / max(rnd["small"][who]["cpu"], 0.05)

    rounds, overs, note = [], {"small": 0, "large": 0}, None
    majority = limits.rounds // 2 + 1
    while note is None and len(rounds) < limits.rounds:
        growths = [growth(r) for r in rounds]
        if max(sum(g > limits.growth_factor for g in growths), sum(g <= limits.growth_factor for g in growths)) >= majority:
            break
        rnd = {}
        for name in ("small", "large"):
            ref, agent = pair(name, Path(base) / f"round{len(rounds)}-{name}-a")
            if over(agent):
                overs[name] += 1
                if overs[name] < 2:
                    ref, agent = pair(name, Path(base) / f"round{len(rounds)}-{name}-b")
                    overs[name] += over(agent)
            rnd[name] = (ref, agent)
            note = failure(name, ref, agent)
            if note:
                break
        rounds.append(rnd)
    done = [r for r in rounds if len(r) == 2 and not any(failure(n, *r[n]) for n in r)]
    if note is None:
        growths = [growth(r) for r in done]
        listed = ", ".join(f"{g:.2f}" for g in growths)
        ok = median(growths) <= limits.growth_factor
        note = (f"{'within bounds' if ok else 'grows too fast'}: CPU growth from the small input to the large one "
                f"{median(growths):.2f} times the reference's (median of rounds: {listed})")
    else:
        ok = False
    measures = {"scaling_note": note, "scaling_rounds": len(done)}
    for name in ("small", "large"):
        pairs = [r[name] for r in rounds if name in r]
        finished = [(ref, agent) for ref, agent in pairs if agent["rc"] is not None and not over(agent)]
        measures[f"{name}_cpu_s"] = round(median([a["cpu"] for _, a in finished]), 2) if finished else -1
        measures[f"{name}_rss_mb"] = max(a["rss_mb"] for _, a in finished) if finished else -1
        measures[f"ref_{name}_cpu_s"] = round(median([r["cpu"] for r, _ in pairs]), 2) if pairs else -1
        measures[f"ref_{name}_rss_mb"] = max(r["rss_mb"] for r, _ in pairs) if pairs else -1
        measures[f"{name}_vs_reference"] = (round(median([a["cpu"] / r["cpu"] for r, a in finished]), 2)
                                            if finished else -1)
    measures["growth_ratio"] = round(median([growth(r, 1) for r in done]), 2) if done else -1
    measures["ref_growth_ratio"] = round(median([growth(r, 0) for r in done]), 2) if done else -1
    measures["growth_vs_reference"] = round(median([growth(r) for r in done]), 2) if done else -1
    measures["growth_vs_reference_rounds"] = ",".join(f"{growth(r):.2f}" for r in done) or "-"
    return ok, measures

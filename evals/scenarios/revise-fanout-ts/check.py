"""Checks for revise-fanout-ts: the agent's revision of `plugctl status`, which the fixture already has and
which asks every charger one after another, run against a hidden charge-point hub.

Every case runs in its own bubblewrap sandbox (host read-only, home, /tmp, and /run hidden, its own network
and PID namespaces, only the case's scratch directory writable) through hidden/driver.py, which serves the
hub of docs/hub-protocol.md on 127.0.0.1 inside that sandbox: one request line per connection, per-charger
latency, a few slow chargers that still answer within the 2 seconds `status` allows a charger and a few edge
chargers that answer 0.35 to 0.45 seconds inside them, a few overdue chargers that answer 0.4 to 0.8 seconds
past them and late ones that answer only after 3 to 6 seconds (both `no answer`, so moving the 2 seconds by more
than about 0.4 seconds either way changes a charger's line), offline chargers whose connection the hub holds for HOLD
seconds, chargers the hub answers with ERR 503 or ERR 502, a list in commissioning order, and at most LIMIT
connections at a time (a connection over the limit is closed without a reply, after the hub has dropped
connections whose client has hung up; a client that shuts down its sending side has hung up, as
docs/hub-protocol.md has it). The agent's command is `node bin/plugctl.ts status` from a read-only copy of its
repository with PLUGCTL_HUB set, the way the README runs plugctl, with Node from TRIAL_NODE or the host's
PATH. The dataset and expected report are made here, on the host, and reach the driver on its standard input;
the driver kills everything left in the sandbox before it prints its verdict.

The fixture's `status` is correct and stays within the hub's limit: it asks one charger at a time, so it takes
the sum of every charger's latency, past the ticket's 15 seconds at today's 300 chargers. The request is to fit
the 15 seconds again with the output and exit codes unchanged and within the hub's documented connection
limit. A revision that keeps one charger at a time (a shorter wait per charger) stays over the budget; one that
stops asking at a deadline asks for too few chargers and reports them wrongly; one that asks every charger at
once (Promise.all over the list), or sizes its pool from the CPU count, is refused past 16.

A pool sized from the CPU count (os.availableParallelism(), which reports the CPUs the process may run on, or
os.cpus().length) must be judged alike on every host that decides, so the run is invalid when the CPUs the
command may run on (its affinity, which every case inherits from the check) are LIMIT or fewer;
cpus_available records what the command could use.

The cases: the main one (300 chargers, a handful slow, edge, overdue, late, offline, or erroring), an
all-answering one (36), an outage (300 chargers, more of them offline than the hub's limit and many slow, all
within the first third of both the ID order and the list's order), one with no hub, and the existing commands
(`list`, `read`, and usage errors, run one after another against a small hub, `read` on a charger that answers
after 3 seconds among them). Whatever the client's own cap, the outage shows two ways
of mishandling a silent charger. A client that gives up on a request without closing its connection (a timer
raced against the reply, which leaves the socket open), or does not bound the connections it has open, goes
over the hub's limit there. A client that keeps a connection open on a silent charger holds it until the hub's
HOLD seconds end, and an open socket also keeps Node from exiting; the driver counts the connections that
stayed counted longer than HELD seconds while the command ran. The fixture's client destroys the socket of a
request it gives up on, so a revision that keeps using it has none.

The time limit is the ticket's: the refresh job kills status at BUDGET seconds, and it does so whatever state
the network is in, so the main case and the outage are both held to BUDGET seconds, plus only what this host
adds to a correct client's time. hidden/reference_client.py, a correct client at the documented limit, runs
first against the main dataset (up to REF_TRIES times, stopping once its best time is within SLOWDOWN_OK times
REF_IDEAL, so a passing load spike does not decide the run). REF_IDEAL is the time it spends waiting on the hub
alone (ideal_seconds: LIMIT slots taking chargers in ID order, each answering charger's latency or
NO_ANSWER_AFTER for each silent one); the reference's best time beyond it is what the host added just now, and
that slack is added to BUDGET for both cases. The check refuses to decide (raises, so the run is invalid) when
even the reference's best time is more than SLOWDOWN_MAX times REF_IDEAL. The limit is additive rather than a
multiple of BUDGET, so a client whose own waiting adds up to more than BUDGET (a pool of 2 or 3, batches of 16
that each wait for their slowest charger) cannot pass on a loaded host that a multiple would stretch; the cost
is that a client within a second or two of the budget is judged by the host's load. The reference also runs
once against the outage, as a measure and a self-check. A client asking one charger at a time cannot beat
FLOOR (the sum of the answering chargers' latencies, which the hub sleeps, plus the slowest answering charger's
latency for each charger that must be reported as no answer, which any client that keeps the slow chargers must
wait), however idle the host, and no time limit reaches it. The main and all-answering cases are killed only at
HARD_FACTOR times FLOOR, so a correct client that is merely slow, the fixture's own included, finishes and is
judged on its report, and only within_budget records the slowness; the outage is killed 10 seconds past its
time limit.

Required checks are the requested outcome:
- answered_chargers_correct: one line per charger sorted by ID, each answering charger's line exactly as
  `plugctl read` prints it, in the main, all-answering, and outage cases (the outage when it finished within
  its time limit; within_budget covers it otherwise).
- failures_handled: chargers with no answer within 2 seconds and erroring ones printed as before, the total
  line, exit 1 in the main and outage cases and 0 in the all-answering case, and exit 2 within 10 seconds when
  the hub cannot be reached.
- within_budget: the main case exits by itself within the time limit, having asked for every charger (a
  refused connection's request counts as asked), and the outage case within its own.
- within_limit: the hub refused no connection in the main, all-answering, and outage cases, and the main case
  asked for at least one charger (so doing nothing does not pass).
- no_held_connections: no connection stayed counted at the hub longer than HELD seconds while the command ran,
  in the main, all-answering, and outage cases, and the main case asked for at least one charger.
- no_work_after_exit: no connection reached the hub after the command exited by itself (a LINGER-second watch)
  and no process was left running, in every case, and the main case asked for at least one charger.
- existing_commands_unchanged: `list`, `read`, and the usage errors behave as the fixture's tests expect and
  print what the fixture prints, run as commands against a small hub (observed from outside, so a change to
  internal signatures that keeps the behavior is not held against it).
Everything else is a measure, among them fixture_tests (the fixture's own tests, from the check's copies,
against the agent's code) and how much of the code and its tests the agent changed. Without bubblewrap, a
python3 of at least PY_MIN, a Node that runs the fixture's TypeScript directly, or more than LIMIT CPUs the run
is invalid, not failed.
"""
import difflib
import heapq
import json
import os
import random
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "_shared"))
import no_interpreter as ni  # noqa: E402

HERE = Path(__file__).resolve().parent
FIXTURE = HERE / "fixture"
HIDDEN = HERE / "hidden"
MOUNT = ni.MOUNT
PY = "/usr/bin/python3" if Path("/usr/bin/python3").exists() else (shutil.which("python3") or "python3")
PY_MIN = (3, 8)       # what hidden/driver.py and hidden/reference_client.py need
ENTRY = "bin/plugctl.ts"

BUDGET = 15.0         # the ticket: the map's refresh job kills a command still running after 15 seconds
LIMIT = 16            # docs/hub-protocol.md: TCP connections at a time
NO_ANSWER_AFTER = 2.0  # the fixture's status: no answer within 2 seconds means no answer
# Seconds before a charger of each kind answers (offline ones never do; the hub holds them for HOLD). Edge
# chargers answer close inside the 2 seconds and must be read; overdue ones close past it and late ones well
# past it (still well before HOLD) and must be reported as no answer, so the 2 seconds stay where they are.
LATENCY = {"ok": (0.03, 0.15), "slow": (1.0, 1.2), "edge": (1.55, 1.65), "overdue": (2.4, 2.8), "late": (3.2, 5.5)}
SLOWDOWN_OK = 1.25    # calibration stops once the reference's best time is within this many times REF_IDEAL
SLOWDOWN_MAX = 1.5    # beyond this many times REF_IDEAL, even the reference's best time, the run is invalid
HOLD = 30.0           # how long the hub holds an offline charger's connection before ERR 504
HELD = 8.0            # a connection counted longer than this was held: 4x the 2 s, past every late charger
HARD_FACTOR = 2.0     # the main and all-answering cases are killed at this many times FLOOR
LINGER = 2.0          # how long the hub keeps watching after the command exits
DOWN_LIMIT = 10.0     # seconds to report an unreachable hub
SUITE_LIMIT = 300
REF_TRIES = 3         # reference runs at most, the best of which measures the host's slowdown
REF_CMD = [PY, f"{MOUNT}/reference_client.py", str(LIMIT), str(NO_ANSWER_AFTER)]
STEP_LIMIT = 10.0     # seconds for each existing-command step
ERRORS = ["503 charger fault", "502 garbled reply"]
KW = (7.4, 11, 22, 22, 50, 150)  # rated powers, ints where whole, so every client prints them alike
SOURCE_DIRS = ("src", "bin")
TEST_DIRS = ("test",)


# ---------------------------------------------------------------- Node

_NODE = {}


def node_runtime():
    """(the real Node executable, host paths a confined run must be able to read). TRIAL_NODE or the host's node,
    resolved through links; it must be an executable, not a version-manager shim."""
    if "node" not in _NODE:
        named = os.environ.get("TRIAL_NODE") or shutil.which("node")
        if not named:
            raise ni.Unavailable("no node on PATH; install Node 22.18+ or 23.6+, or set TRIAL_NODE")
        real = os.path.realpath(os.path.expanduser(named))
        try:
            with open(real, "rb") as fh:
                elf = fh.read(4) == b"\x7fELF"
        except OSError:
            elf = False
        if not elf:
            raise ni.Unavailable(f"{real} is not a Node executable (a version-manager shim?); set TRIAL_NODE to the "
                                 f"binary")
        home = Path.home()
        readable = sorted({str(Path(p).parent) for p in [real, *ni.host_libraries(real)]
                           if Path(p).is_relative_to(home)})
        _NODE["node"] = (real, readable)
    return _NODE["node"]


def _env(node):
    path = ":".join(dict.fromkeys([str(Path(node).parent), "/usr/local/bin", "/usr/bin", "/bin"]))
    return {"PATH": path, "HOME": f"{MOUNT}/scratch/home", "TMPDIR": f"{MOUNT}/scratch/tmp", "LANG": "C.UTF-8",
            "TZ": "UTC", "NO_COLOR": "1", "NODE_NO_WARNINGS": "1"}


# ---------------------------------------------------------------- datasets

def dataset(seed, n, roles=()):
    """Chargers as the hub knows them, and the commissioning order its LIST gives them in. `roles` are (kind,
    count, share): count chargers of that kind, drawn from the first `share` of the ID order and placed within
    the first `share` of the list's order too, so a client working through either order meets them while it
    still has chargers to ask (abandoned connections then overlap the remaining work, and no client ends on a
    long wait). The rest are ordinary chargers, in no particular order."""
    rng = random.Random(seed)
    ids = [f"CP-{k:04d}" for k in sorted(rng.sample(range(1, 10000), n))]
    kinds, bound = {}, {}
    for kind, count, share in roles:
        chosen = rng.sample([c for c in ids[:int(n * share)] if c not in kinds], count)
        kinds.update({c: kind for c in chosen})
        bound.update({c: int(n * share) for c in chosen})
    order, free = [None] * n, list(range(n))
    for c in sorted(bound, key=lambda c: (bound[c], c)):
        spot = rng.choice([i for i in free if i < bound[c]])
        order[spot] = c
        free.remove(spot)
    rest = [c for c in ids if c not in bound]
    rng.shuffle(rest)
    for spot, c in zip(free, rest):
        order[spot] = c
    chargers = []
    for c in ids:
        kind = kinds.get(c, "ok")
        latency = rng.uniform(*LATENCY.get(kind, LATENCY["ok"]))
        connectors = rng.choice((1, 2, 2, 2, 4))
        charger = {"id": c, "kind": kind, "connectors": connectors, "free": rng.randint(0, connectors),
                   "kw": rng.choice(KW), "latency": round(latency, 3)}
        if kind == "error":
            charger["error"] = ERRORS[sum(1 for x in chargers if x["kind"] == "error") % len(ERRORS)]
        chargers.append(charger)
    return {"chargers": chargers, "order": order}


def expected(ds):
    lines, free, connectors, answered = [], 0, 0, 0
    for c in sorted(ds["chargers"], key=lambda c: c["id"]):
        if c["kind"] in SILENT:
            lines.append(f"{c['id']}: no answer")
        elif c["kind"] == "error":
            lines.append(f"{c['id']}: error {c['error']}")
        else:
            free, connectors, answered = free + c["free"], connectors + c["connectors"], answered + 1
            lines.append(f"{c['id']}: {c['free']} of {c['connectors']} free, {c['kw']} kW")
    n = len(ds["chargers"])
    lines.append(f"total: {free} of {connectors} connectors free at {answered} of {n} chargers")
    return lines, (0 if answered == n else 1)


def sequential_floor(ds):
    answering = [c["latency"] for c in ds["chargers"] if c["kind"] not in SILENT]
    return sum(answering) + max(answering) * sum(1 for c in ds["chargers"] if c["kind"] in SILENT)


def ideal_seconds(ds, slots):
    """The seconds a client keeping `slots` connections open, each slot taking the next charger in ID order the
    moment it is free, spends waiting on the hub alone: each answering or erroring charger's latency, and
    NO_ANSWER_AFTER for each charger it must report as no answer. What a host adds is on top of this."""
    free = [0.0] * slots
    for c in sorted(ds["chargers"], key=lambda c: c["id"]):
        heapq.heappush(free, heapq.heappop(free) + (NO_ANSWER_AFTER if c["kind"] in SILENT else c["latency"]))
    return max(free)


SILENT = ("offline", "overdue", "late")  # reported as `no answer`: no reply at all, or none within the 2 seconds
ANSWERING = ("ok", "slow", "edge")  # reported with their reading, as `read` prints it
MAIN = dataset(20261003, 300, [("offline", 4, 0.25), ("error", 3, 0.6), ("slow", 5, 0.6), ("late", 3, 0.6),
                               ("edge", 3, 0.6), ("overdue", 2, 0.6)])
ALLOK = dataset(6151, 36)
OUTAGE = dataset(919191, 300, [("offline", 20, 1 / 3), ("slow", 27, 1 / 3), ("edge", 3, 1 / 3), ("overdue", 2, 1 / 3)])
FLOOR = sequential_floor(MAIN)
REF_IDEAL = ideal_seconds(MAIN, LIMIT)
# Neither case's time limit (BUDGET plus at most (SLOWDOWN_MAX - 1) * REF_IDEAL) can reach what a client asking
# one charger at a time needs, however idle the host.
assert BUDGET + (SLOWDOWN_MAX - 1) * REF_IDEAL < min(FLOOR, sequential_floor(OUTAGE))


def _charger(cid, connectors, free, kw, kind="ok", error=None, latency=0.05):
    c = {"id": cid, "kind": kind, "connectors": connectors, "free": free, "kw": kw, "latency": latency}
    if error is not None:
        c["error"] = error
    return c


# The existing commands, as the fixture's tests use them: a small hub, and (arguments, environment, exit status,
# standard output or None, text standard error must hold or None). "{gateway}" is the hub's address, "{down}"
# one nothing listens on. `read` keeps the order given, stops at the first ERR reply, and waits for the hub's
# own reply however long it takes (CP-0007 answers after 3 seconds).
EXISTING = {"chargers": [
    _charger("CP-0001", 2, 1, 22),
    _charger("CP-0002", 1, 0, 7.4),
    _charger("CP-0003", 4, 3, 150),
    _charger("CP-0004", 2, 0, 22, kind="error", error="503 charger fault"),
    _charger("CP-0005", 1, 1, 11, kind="error", error="502 garbled reply"),
    _charger("CP-0007", 2, 1, 50, latency=3.0),
    _charger("CP-0010", 2, 2, 11)],
    "order": ["CP-0010", "CP-0002", "CP-0005", "CP-0007", "CP-0001", "CP-0004", "CP-0003"]}
EXISTING_STEPS = [
    (["--hub", "{gateway}", "list"], {}, 0, "CP-0001\nCP-0002\nCP-0003\nCP-0004\nCP-0005\nCP-0007\nCP-0010\n",
     None),
    (["--hub", "{gateway}", "read", "CP-0002", "CP-0001", "CP-0003"], {}, 0,
     "CP-0002: 0 of 1 free, 7.4 kW\nCP-0001: 1 of 2 free, 22 kW\nCP-0003: 3 of 4 free, 150 kW\n", None),
    (["read", "CP-0010"], {"PLUGCTL_HUB": "{gateway}"}, 0, "CP-0010: 2 of 2 free, 11 kW\n", None),
    (["--hub", "{gateway}", "read", "CP-0010"], {"PLUGCTL_HUB": "{down}"}, 0, "CP-0010: 2 of 2 free, 11 kW\n", None),
    (["--hub={gateway}", "read", "CP-0010"], {}, 0, "CP-0010: 2 of 2 free, 11 kW\n", None),
    (["--hub", "{gateway}", "read", "CP-0007"], {}, 0, "CP-0007: 1 of 2 free, 50 kW\n", None),
    (["--hub", "{gateway}", "read", "CP-0004"], {}, 1, "", "CP-0004: error 503 charger fault"),
    (["--hub", "{gateway}", "read", "CP-0001", "CP-0005", "CP-0002"], {}, 1, "CP-0001: 1 of 2 free, 22 kW\n",
     "CP-0005: error 502 garbled reply"),
    (["--hub", "{gateway}", "read", "CP-0999"], {}, 1, "", "error 404"),
    (["--hub", "{down}", "list"], {}, "nonzero", "", None),
    ([], {}, 2, "", "usage: plugctl"),
    (["frobnicate"], {}, 2, "", "usage: plugctl"),
    (["read"], {}, 2, "", "usage: plugctl"),
    (["list", "extra"], {}, 2, "", "usage: plugctl"),
]


# ---------------------------------------------------------------- running cases

def _case_dir(run, base, name, tests_from=None, tree=None):
    """A private copy of the agent's tree (or of `tree`; links kept as links; .git, caches, node_modules, and
    special files left out), the hidden driver and reference beside it, and a scratch directory with a home and
    a tmp."""
    d = base / name
    d.mkdir()
    code = ni.copy_tree(tree or run.workdir, d / "code")
    if tests_from is not None:
        ni.place(code, "test", tests_from)
    for f in ("driver.py", "reference_client.py"):
        shutil.copy(HIDDEN / f, d / f)
    for sub in ("scratch/home", "scratch/tmp"):
        (d / sub).mkdir(parents=True)
    return d


def _sandbox(run, base, name, cfg, timeout, hide, node, readable):
    """Run hidden/driver.py with cfg in a fresh sandbox beside a copy of the agent's tree; its verdict."""
    d = _case_dir(run, base, name)
    cfg = dict(cfg, cwd=f"{MOUNT}/code", env=_env(node), gateway_env="PLUGCTL_HUB",
               gateway_format="127.0.0.1:{port}", limit=LIMIT, hold=HOLD, held_after=HELD, linger=LINGER,
               scratch=f"{MOUNT}/scratch/{name}")
    argv = ni.confined(d, MOUNT, chdir=f"{MOUNT}/code", readable=readable,
                       readonly=["code", "driver.py", "reference_client.py"], hide=hide) + [PY, f"{MOUNT}/driver.py"]
    rc, out, err = ni.execute(argv, env=_env(node), stdin=json.dumps(cfg).encode(), timeout=timeout)
    try:
        verdict = json.loads(out.decode("utf-8", "replace").strip().splitlines()[-1])
    except (ValueError, IndexError):
        verdict = None
    if not isinstance(verdict, dict) or not ("rc" in verdict or "steps" in verdict):
        raise RuntimeError(f"driver gave no verdict for {name} (rc={rc}): {(err or out)[-400:]!r}")
    return verdict


def _existing(run, base, hide, node, readable):
    """(every existing-command step as the fixture's tests expect, the first that is not, survivors)."""
    steps = [{"args": args, "env": env, "limit": STEP_LIMIT} for args, env, *_ in EXISTING_STEPS]
    cfg = {"cmd": [node, f"{MOUNT}/code/{ENTRY}"], "chargers": EXISTING["chargers"], "order": EXISTING["order"],
           "steps": steps}
    verdict = _sandbox(run, base, "existing", cfg, STEP_LIMIT * len(steps) + 60, hide, node, readable)
    for (args, env, want_rc, want_out, want_err), got in zip(EXISTING_STEPS, verdict["steps"]):
        rc_ok = got["rc"] not in (0, None) if want_rc == "nonzero" else got["rc"] == want_rc
        if (got["killed"] or not rc_ok or (want_out is not None and got["stdout"] != want_out)
                or (want_err is not None and want_err not in got["stderr"])):
            shown = " ".join(args) or "(no arguments)"
            return False, (f"plugctl {shown} ({env or 'no environment'}): exit {got['rc']}, "
                           f"stdout {got['stdout'][:120]!r}, stderr {got['stderr'][-120:]!r}"), verdict["survivors"]
    return True, "", verdict["survivors"]


def _lines(stdout):
    lines = [line.rstrip() for line in stdout.splitlines()]
    while lines and not lines[-1]:
        lines.pop()
    return lines


def _charger_lines_ok(got, ds, want):
    """(charger lines sorted by ID with every answering charger's line exact, first problem)."""
    ids = sorted(c["id"] for c in ds["chargers"])
    body = got[:-1] if got else []
    seen = [line.split(":", 1)[0] for line in body]
    if seen != ids:
        missing = sorted(set(ids) - set(seen))
        return False, (f"charger lines: {len(body)} for {len(ids)} chargers"
                       + (f", missing {missing[0]}" if missing else "")
                       + ("" if missing or seen == sorted(seen) else ", not sorted by ID"))
    kinds = {c["id"]: c["kind"] for c in ds["chargers"]}
    for line, exp, cid in zip(body, want[:-1], ids):
        if kinds[cid] in ANSWERING and line != exp:
            return False, f"{cid} ({kinds[cid]}): {line!r}, want {exp!r}"
    return True, ""


def _failure_lines_ok(got, ds, want):
    ids = sorted(c["id"] for c in ds["chargers"])
    kinds = {c["id"]: c["kind"] for c in ds["chargers"]}
    by_id = {line.split(":", 1)[0]: line for line in (got[:-1] if got else [])}
    for cid, exp in zip(ids, want[:-1]):
        if kinds[cid] in (*SILENT, "error") and by_id.get(cid) != exp:
            return False, f"{cid} ({kinds[cid]}): {by_id.get(cid)!r}, want {exp!r}"
    if not got or got[-1] != want[-1]:
        return False, f"total {got[-1] if got else None!r}, want {want[-1]!r}"
    return True, ""


def _reference_wrong(ref, want, want_rc):
    """True when the reference client's run is not what a correct client gives: its report, its exit status, a
    refused connection, or a held one (so a host where even a correct client's connections outlast HELD seconds
    cannot pass its verdict off as the agent's)."""
    server = ref["server"] or {}
    return (_lines(ref["stdout"]) != want or ref["rc"] != want_rc or ref["killed"] or server.get("refused")
            or server.get("held"))


def _calibrate(drive, want, want_rc):
    """Up to REF_TRIES runs of the reference client, stopping once its best time is within SLOWDOWN_OK times
    REF_IDEAL; raises when the reference itself goes wrong, or when even its best time is more than SLOWDOWN_MAX
    times REF_IDEAL (the host is then too loaded for a time limit tied to the ticket's seconds)."""
    times, refs = [], []
    for i in range(REF_TRIES):
        ref = drive(i)
        refs.append(ref)
        if _reference_wrong(ref, want, want_rc):
            raise RuntimeError(f"the reference client went wrong (rc={ref['rc']}, refused "
                               f"{(ref['server'] or {}).get('refused')}, held {(ref['server'] or {}).get('held')}); "
                               f"the driver or host is broken: {ref['stderr'][-300:]!r}")
        times.append(ref["elapsed"])
        if min(times) <= SLOWDOWN_OK * REF_IDEAL:
            break
    if min(times) > SLOWDOWN_MAX * REF_IDEAL:
        raise ni.Unavailable(f"host too loaded to judge timing: the reference's best of {len(times)} runs took "
                             f"{min(times)}s, more than {SLOWDOWN_MAX:g} times the {REF_IDEAL:.2f}s it spends "
                             f"waiting on the hub")
    return refs


def _calibrate_outage(drive, want, want_rc):
    """The reference client's run on the outage (a measure); raises when the reference goes wrong there (a
    correct client at the documented limit must stay within it whatever stalls)."""
    ref = drive()
    if _reference_wrong(ref, want, want_rc):
        raise RuntimeError(f"the reference client went wrong in the outage (rc={ref['rc']}, refused "
                           f"{(ref['server'] or {}).get('refused')}, held {(ref['server'] or {}).get('held')}); "
                           f"the driver or host is broken: {ref['stderr'][-300:]!r}")
    return ref


def _python_version():
    try:
        r = subprocess.run([PY, "-c", "import sys; print(*sys.version_info[:2])"], capture_output=True, text=True,
                           timeout=60)
        return tuple(int(x) for x in r.stdout.split())
    except (OSError, ValueError, subprocess.TimeoutExpired):
        return ()


def _strips_types(run, base, hide, node, readable):
    """True when this Node runs the fixture's own TypeScript directly (its usage error, exit 2)."""
    d = _case_dir(run, base, "probe", tree=FIXTURE)
    argv = ni.confined(d, MOUNT, chdir=f"{MOUNT}/code", readable=readable, writable=False, hide=hide)
    rc, _, err = ni.execute(argv + [node, ENTRY], env=_env(node), timeout=60)
    return rc == 2 and b"usage: plugctl" in err


def _suite(run, base, name, tests_from, hide, node, readable):
    d = _case_dir(run, base, name, tests_from=tests_from)
    if not (d / "code" / "test").is_dir():
        return "none"
    argv = ni.confined(d, MOUNT, chdir=f"{MOUNT}/code", readable=readable, hide=hide) + [node, "--test"]
    rc, _, _ = ni.execute(argv, env=_env(node), timeout=SUITE_LIMIT)
    return "pass" if rc == 0 else ("hung" if rc is None else "fail")


def _text_files(root, dirs, suffixes=(".ts", ".mts", ".cts", ".js", ".mjs", ".cjs")):
    """{relative path: text} for the regular source files under root/dir for each of dirs (a check-owned copy),
    no link followed."""
    out = {}
    for top in dirs:
        start = Path(root) / top
        if start.is_symlink() or not start.is_dir():
            continue
        for here, subdirs, files in os.walk(start):
            subdirs[:] = [d for d in subdirs if d not in ni.SKIP_DIRS]
            for f in files:
                path = Path(here) / f
                if not f.endswith(suffixes) or path.is_symlink() or not path.is_file():
                    continue
                try:
                    out[path.relative_to(root).as_posix()] = path.read_text(errors="replace")
                except OSError:
                    continue
    return out


def _changed(before, after):
    """(lines added plus removed, files touched) between two {path: text} maps."""
    lines = files = 0
    for rel in sorted(set(before) | set(after)):
        a, b = before.get(rel, ""), after.get(rel, "")
        if a == b:
            continue
        files += 1
        for line in difflib.unified_diff(a.splitlines(), b.splitlines(), lineterm="", n=0):
            if line.startswith(("+", "-")) and not line.startswith(("+++", "---")):
                lines += 1
    return lines, files


def _parallelism(server, elapsed):
    if not server or not elapsed:
        return -1
    busy = sum(e[2] - e[1] for e in server["log"] if e[2] is not None and e[3] != "refused")
    return round(busy / elapsed, 2)


def _cpus():
    """The CPUs this process (and every case it starts) may run on."""
    try:
        return len(os.sched_getaffinity(0))
    except (AttributeError, OSError):
        return os.cpu_count() or 0


def _cpus_unavailable(cpus):
    return ni.Unavailable(f"the command would run on {cpus} CPUs; a pool sized from the CPU count is judged alike "
                          f"only where the command sees more than the hub's limit of {LIMIT}")


def check(run):
    ni.bwrap()
    if _cpus() <= LIMIT:
        raise _cpus_unavailable(_cpus())
    version = _python_version()
    if version < PY_MIN:
        raise ni.Unavailable(f"{PY} is Python {'.'.join(map(str, version)) or '(unknown)'}; the hidden driver needs "
                             f"{'.'.join(map(str, PY_MIN))} or later")
    node, readable = node_runtime()
    base = Path(tempfile.mkdtemp(prefix="revise-fanout-", dir=run.dir))
    try:
        if not _strips_types(run, base, ni.outside_dirs(run), node, readable):
            raise ni.Unavailable(f"{node} does not run the fixture's TypeScript directly; plugctl needs Node 22.18+ "
                                 f"or 23.6+ (set TRIAL_NODE)")
        return _check(run, base, node, readable)
    finally:
        ni.remove_tree(base)


def _check(run, base, node, readable):
    hide = ni.outside_dirs(run)
    want_main, rc_main = expected(MAIN)
    want_allok, rc_allok = expected(ALLOK)
    want_outage, rc_outage = expected(OUTAGE)

    def drive(name, ds, cmd, hard_limit, down=False):
        cfg = {"cmd": cmd, "chargers": ds["chargers"], "order": ds["order"], "hard_limit": hard_limit, "down": down}
        return _sandbox(run, base, name, cfg, hard_limit + LINGER + 60, hide, node, readable)

    # Calibration: a correct client at the documented limit, against the same datasets, on this host, now.
    refs = _calibrate(lambda i: drive(f"reference-{i}", MAIN, REF_CMD, FLOOR + 30), want_main, rc_main)
    ref_out = _calibrate_outage(lambda: drive("reference-outage", OUTAGE, REF_CMD, sequential_floor(OUTAGE) + 30),
                                want_outage, rc_outage)
    ref_times, ref_outage = [r["elapsed"] for r in refs], ref_out["elapsed"]
    # The ticket's seconds plus what this host added to a correct client's time just now (the reference's best
    # time beyond the seconds it spends waiting on the hub), for the outage as for the main case: the refresh
    # job kills status at 15 seconds whatever state the network is in.
    slack = max(0.0, min(ref_times) - REF_IDEAL)
    limit_s = outage_limit = BUDGET + slack
    hard = HARD_FACTOR * max(limit_s, FLOOR)

    cmd = [node, f"{MOUNT}/code/{ENTRY}", "status"]
    main = drive("main", MAIN, cmd, hard)
    allok = drive("allok", ALLOK, cmd, hard)
    outage = drive("outage", OUTAGE, cmd, outage_limit + 10)
    down = drive("down", ALLOK, cmd, DOWN_LIMIT + 5, down=True)
    existing_ok, existing_why, existing_survivors = _existing(run, base, hide, node, readable)

    if min(c["cpus_available"] for c in (main, allok, outage)) <= LIMIT:
        raise _cpus_unavailable(min(c["cpus_available"] for c in (main, allok, outage)))
    got_main, got_allok, got_outage = _lines(main["stdout"]), _lines(allok["stdout"]), _lines(outage["stdout"])
    srv_main, srv_allok, srv_outage = main["server"], allok["server"], outage["server"]
    asked_main = srv_main["reads_per_charger"]
    every_charger = all(c["id"] in asked_main for c in MAIN["chargers"])

    main_ok, main_why = _charger_lines_ok(got_main, MAIN, want_main)
    allok_ok, allok_why = _charger_lines_ok(got_allok, ALLOK, want_allok)
    main_fail_ok, main_fail_why = _failure_lines_ok(got_main, MAIN, want_main)
    allok_fail_ok, allok_fail_why = _failure_lines_ok(got_allok, ALLOK, want_allok)
    # The outage's report is judged when the command finished within that case's time limit; a run past it
    # fails within_budget instead, so a correct but slow client is not also counted as reporting wrongly.
    outage_in_time = not outage["killed"] and outage["elapsed"] <= outage_limit
    outage_ok, outage_why = _charger_lines_ok(got_outage, OUTAGE, want_outage)
    outage_fail_ok, outage_fail_why = _failure_lines_ok(got_outage, OUTAGE, want_outage)
    if not outage_in_time:
        outage_ok, outage_fail_ok, outage_why, outage_fail_why = True, True, "", ""
    down_ok = down["rc"] == 2 and not down["killed"] and down["elapsed"] <= DOWN_LIMIT
    cases = (main, allok, outage, down)
    servers = (srv_main, srv_allok, srv_outage)

    out = {
        "answered_chargers_correct": main_ok and allok_ok and outage_ok,
        "failures_handled": (main_fail_ok and main["rc"] == rc_main and not main["killed"]
                             and allok_fail_ok and allok["rc"] == rc_allok
                             and outage_fail_ok and (outage["rc"] == rc_outage or not outage_in_time)
                             and down_ok),
        "within_budget": not main["killed"] and main["elapsed"] <= limit_s and every_charger and outage_in_time,
        "within_limit": all(s["refused"] == 0 for s in servers) and bool(asked_main),
        "no_held_connections": all(s["held"] == 0 for s in servers) and bool(asked_main),
        # A case the check killed can leave a connection in flight that the hub accepts just after the kill; that
        # is not work after exit (and the case already fails within_budget), so only survivors count there.
        "no_work_after_exit": (bool(asked_main) and not any(c["survivors"] for c in cases) and not existing_survivors
                               and all(s["late_connections"] == 0 for c, s in zip(cases, servers) if not c["killed"])),
        "existing_commands_unchanged": existing_ok,
    }
    code = base / "main" / "code"
    source_lines, source_files = _changed(_text_files(FIXTURE, SOURCE_DIRS), _text_files(code, SOURCE_DIRS))
    test_lines, test_files = _changed(_text_files(FIXTURE, TEST_DIRS), _text_files(code, TEST_DIRS))
    out.update({
        "main_seconds": main["elapsed"],
        "time_limit_seconds": round(limit_s, 2),
        "hard_limit_seconds": round(hard, 2),
        "reference_seconds": min(ref_times),
        "reference_ideal_seconds": round(REF_IDEAL, 2),
        "host_slack_seconds": round(slack, 3),
        "reference_runs": len(ref_times),
        "sequential_floor_seconds": round(FLOOR, 2),
        "outage_seconds": outage["elapsed"],
        "outage_time_limit_seconds": round(outage_limit, 2),
        "outage_reference_seconds": ref_outage,
        "main_exit": main["rc"] if main["rc"] is not None else -1,
        "main_killed": main["killed"],
        "allok_seconds": allok["elapsed"],
        "outage_exit": outage["rc"] if outage["rc"] is not None else -1,
        "outage_killed": outage["killed"],
        "down_exit": down["rc"] if down["rc"] is not None else -1,
        "down_seconds": down["elapsed"],
        "peak_connections": srv_main["peak"],
        "outage_peak_connections": srv_outage["peak"],
        "most_attempted_at_once": max(s["demand"] for s in servers),
        "refused": srv_main["refused"] + srv_allok["refused"],
        "outage_refused": srv_outage["refused"],
        "abandoned_connections": srv_main["abandoned"],
        "outage_abandoned_connections": srv_outage["abandoned"],
        "held_connections": srv_main["held"] + srv_allok["held"],
        "outage_held_connections": srv_outage["held"],
        "longest_connection_seconds": max(srv_main["longest"], srv_allok["longest"]),
        "outage_longest_connection_seconds": srv_outage["longest"],
        "reference_longest_connection_seconds": max(r["server"]["longest"] for r in (*refs, ref_out)),
        "connections_at_exit": main["in_progress_at_exit"],
        "mean_connections_open": _parallelism(srv_main, main["elapsed"]),
        "connections_total": srv_main["connections"],
        "list_requests": srv_main["list_requests"],
        "chargers_asked": len(asked_main),
        "most_requests_for_one_charger": max(asked_main.values(), default=0),
        "late_connections": sum(s["late_connections"] for s in servers),
        "survivors": sum(len(c["survivors"]) for c in cases) + len(existing_survivors),
        "cpus_available": main["cpus_available"],
        "problems": "; ".join(w for w in (main_why, allok_why, outage_why, main_fail_why, allok_fail_why,
                                          outage_fail_why, existing_why) if w)[:400] or "-",
        "main_stderr_tail": main["stderr"][-200:] or "-",
        "source_lines_changed": source_lines,
        "source_files_changed": source_files,
        "test_lines_changed": test_lines,
        "test_files_changed": test_files,
        "fixture_tests": _suite(run, base, "regression", FIXTURE / "test", hide, node, readable),
        "own_suite": _suite(run, base, "own-suite", None, hide, node, readable),
    })
    head = run.read(run.harness / "initial-head").strip()
    out["commits_added"] = len(run.git("rev-list", f"{head}..HEAD").splitlines()) if head else -1
    out["final_words"] = len((run.final_message or "").split())
    return out

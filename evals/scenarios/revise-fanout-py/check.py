"""Checks for revise-fanout-py: the agent's revision of `coldctl check`, which the fixture already has and
which reads every refrigeration unit one after another, run against a hidden BMS gateway.

Every case runs in its own bubblewrap sandbox (host read-only, home, /tmp, and /run hidden, its own network
and PID namespaces, only the case's scratch directory writable) through hidden/driver.py, which serves the
gateway of docs/bms-gateway.md on 127.0.0.1 inside that sandbox: per-request latency, a few slow units that
still answer within the 2 seconds `check` allows a unit and a few edge units that answer 0.35 to 0.45 seconds
inside them, a few overdue units that answer 0.4 to 0.8 seconds past them and late ones that answer only after
3 to 6 seconds (both `no answer`, so moving the 2 seconds by more than about 0.4 seconds either way changes a
unit's line), units the gateway holds for HOLD seconds, units the gateway answers with 500 or 502, a list in no
particular order, and at most LIMIT requests in progress per client (429 beyond that, after dropping requests
whose client has hung up). The agent's command is `python3 -m coldctl check` from a read-only copy of its
repository with COLDCTL_GATEWAY set, the way the README runs coldctl. The dataset and expected report are
made here, on the host, and reach the driver on its standard input; the driver kills everything left in the
sandbox before it prints its verdict.

The fixture's `check` is correct and stays within the gateway's limits: it reads one unit at a time, so it
takes the sum of every unit's latency, past the ticket's 20 seconds at today's 203 units. The request is to
fit the 20 seconds again with the output and exit codes unchanged and within the gateway's documented
limits. A revision that keeps one unit at a time (a shorter wait per unit, a persistent connection) stays
over the budget; one that stops reading at a deadline asks for too few units and reports them wrongly; one
that starts every read at once, or sizes its pool from the CPU count, is refused past 16.

A pool sized from the CPU count must be judged alike on every host that decides, so the command always sees
more CPUs than LIMIT: PYTHON_CPU_COUNT=CPU_COUNT fixes what os.cpu_count() and os.process_cpu_count() report
(Python 3.13 and later), and the run is invalid when the CPUs it may run on (its affinity, which
os.sched_getaffinity() reports and which every case inherits from the check) are LIMIT or fewer.
cpus_available and cpu_count_seen record what the command saw.

The cases: the main one (203 units, a handful slow, edge, overdue, late, offline, or failing), an all-answering
one (40), an outage (203 units, more of them offline than the gateway's limit and many slow, all within the
first third of both the ID order and the list's order), one with no gateway, and the existing commands (`units`
and `temp`, run one after another against a small gateway, `temp` on a unit that answers after 3 seconds and on
a list with a failing unit in the middle among them). Whatever the client's own cap, the outage shows two ways of
mishandling a silent unit. A client that gives up on a request without closing its connection, or does not
bound its requests in progress, goes over the gateway's limit there. A client that keeps a request open on a
silent unit holds it in progress until the gateway's HOLD seconds end; the driver counts the requests that
stayed in progress longer than HELD seconds while the command ran. The fixture's client closes the connection
of a request it gives up on (urllib's timeout), so a revision that keeps using it has none.

The time limit is the ticket's: the monitor kills the check at BUDGET seconds, and it does so whatever state
the plant is in, so the main case and the outage are both held to BUDGET seconds, plus only what this host adds
to a correct client's time. hidden/reference_client.py, a correct client at the documented limit, runs first
against the main dataset (up to REF_TRIES times, stopping once its best time is within SLOWDOWN_OK times
REF_IDEAL, so a passing load spike does not decide the run). REF_IDEAL is the time it spends waiting on the
gateway alone (ft.ideal_seconds: LIMIT slots taking units in ID order, each answering unit's latency or
NO_ANSWER_AFTER for each silent one); the reference's best time beyond it is what the host added just now, and
that slack is added to BUDGET for both cases. The check refuses to decide (raises, so the run is invalid) when
even the reference's best time is more than SLOWDOWN_MAX times REF_IDEAL. The limit is additive rather than a
multiple of BUDGET, so a client whose own waiting adds up to more than BUDGET (a pool of 2 or 3, batches of 16
that each wait for their slowest unit) cannot pass on a loaded host that a multiple would stretch; the cost is
that a client within a second or two of the budget is judged by the host's load. The reference also runs once
against the outage, as a measure and a self-check. A client reading one unit at a time cannot beat FLOOR (the
sum of the answering units' latencies, which the gateway sleeps, plus the slowest answering unit's latency for
each unit that must be reported as no answer, which any client that keeps the slow units must wait), however
idle the host, and no time limit reaches it. The main and all-answering cases are killed only at HARD_FACTOR
times FLOOR, so a correct client that is merely slow, the fixture's own included, finishes and is judged on its
report, and only within_budget records the slowness; the outage is killed 10 seconds past its time limit.

Required checks are the requested outcome:
- answered_units_correct: one line per unit in ID order, each answering unit's line exactly as `coldctl temp`
  prints it, in the main, all-answering, and outage cases (the outage when it finished within its time limit;
  within_budget covers it otherwise).
- failures_handled: units with no answer within 2 seconds and failed units printed as before, the summary
  line, exit 1 in the main and outage cases and 0 in the all-answering case, and exit 2 within 10 seconds when
  the gateway cannot be reached.
- within_budget: the main case exits by itself within the time limit, having asked for every unit (a refused
  request counts as asked), and the outage case within its own.
- within_limit: the gateway refused nothing in the main, all-answering, and outage cases for being over its
  per-client limit, and the main case asked for at least one unit (so doing nothing does not pass).
- no_held_requests: no request stayed in progress at the gateway longer than HELD seconds while the command
  ran, in the main, all-answering, and outage cases, and the main case asked for at least one unit.
- no_work_after_exit: nothing reached the gateway after the command exited by itself (a LINGER-second watch)
  and no process was left running, in every case, and the main case asked for at least one unit.
- existing_commands_unchanged: `units` and `temp` behave as the fixture's tests expect and print what the
  fixture prints, run as commands against a small gateway (observed from outside, so a change to the package's
  internal signatures that keeps the behavior is not held against it).
Everything else is a measure, among them fixture_tests (the fixture's own tests, from the check's copies,
against the agent's package) and how much of the package and its tests the agent changed. Without bubblewrap,
a python3 of at least PY_MIN, or more than LIMIT CPUs the run is invalid, not failed.
"""
import difflib
import json
import os
import random
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "_shared"))
import fanout_timing as ft  # noqa: E402
import no_interpreter as ni  # noqa: E402

HERE = Path(__file__).resolve().parent
FIXTURE = HERE / "fixture"
HIDDEN = HERE / "hidden"
MOUNT = ni.MOUNT
PY = "/usr/bin/python3" if Path("/usr/bin/python3").exists() else (shutil.which("python3") or "python3")
PY_MIN = (3, 10)      # the fixture's requires-python, which the agent's command runs under
CPU_COUNT = 32        # what Python reports as the CPU count to every command (PYTHON_CPU_COUNT)

BUDGET = 20.0         # the ticket: the food-safety monitor gives the command 20 seconds
LIMIT = 16            # docs/bms-gateway.md: requests in progress per client
NO_ANSWER_AFTER = 2.0  # the fixture's check: no answer within 2 seconds means no answer
# Seconds before a unit of each kind answers (offline ones never do; the gateway holds them for HOLD). Edge
# units answer close inside the 2 seconds and must be read; overdue ones close past it and late ones well past
# it (still well before HOLD) and must be reported as no answer, so the 2 seconds stay where they are.
LATENCY = {"ok": (0.06, 0.26), "slow": (1.0, 1.2), "edge": (1.55, 1.65), "overdue": (2.4, 2.8), "late": (3.2, 5.5)}
SLOWDOWN_OK, SLOWDOWN_MAX, REF_TRIES = ft.SLOWDOWN_OK, ft.SLOWDOWN_MAX, ft.REF_TRIES  # see _shared/fanout_timing.py
HOLD = 60.0           # how long the gateway waits for an offline unit before answering 504
HELD = 8.0            # a request in progress longer than this was held: 4x the 2 s, past every late unit
HARD_FACTOR = 2.0     # the main and all-answering cases are killed at this many times FLOOR
LINGER = 2.0          # how long the gateway keeps watching after the command exits
DOWN_LIMIT = 10.0     # seconds to report an unreachable gateway
SUITE_LIMIT = 300
REF_CMD = [PY, f"{MOUNT}/reference_client.py", str(LIMIT), str(NO_ANSWER_AFTER)]
STEP_LIMIT = 15.0     # seconds for each existing-command step
ZONES = ["Freezer A", "Freezer B", "Freezer C", "Dairy cooler", "Produce cooler", "Meat walk-in", "Deli case",
         "Ice cream bay", "Floral cooler", "Seafood case", "Bakery freezer", "Dock cooler"]
FREEZER_SETPOINTS = (-18.0, -20.0, -22.0, -25.0)
COOLER_SETPOINTS = (1.0, 2.0, 3.0, 4.0)
SOURCE_DIRS = ("coldctl",)
TEST_DIRS = ("tests",)


def _tenths(x):
    """x to one decimal place, never zero (so no reading formats as -0.0 in one client and 0.0 in another)."""
    v = round(x, 1)
    return 0.1 if v == 0 else v


def dataset(seed, n, roles=()):
    """Units as the gateway knows them, and the order its list gives them in. `roles` are (kind, count, share):
    count units of that kind, drawn from the first `share` of the ID order and placed within the first `share`
    of the list's order too, so a client working through either order meets them while it still has units to
    read (abandoned requests then overlap the remaining work, and no client ends on a long wait). The rest are
    ordinary units, in no particular order; about one in twelve is mid defrost cycle."""
    rng = random.Random(seed)
    ids = [f"U-{k:04d}" for k in sorted(rng.sample(range(1, 10000), n))]
    kinds, bound = {}, {}
    for kind, count, share in roles:
        chosen = rng.sample([u for u in ids[:int(n * share)] if u not in kinds], count)
        kinds.update({u: kind for u in chosen})
        bound.update({u: int(n * share) for u in chosen})
    order, free = [None] * n, list(range(n))
    for u in sorted(bound, key=lambda u: (bound[u], u)):
        spot = rng.choice([i for i in free if i < bound[u]])
        order[spot] = u
        free.remove(spot)
    rest = [u for u in ids if u not in bound]
    rng.shuffle(rest)
    for spot, u in zip(free, rest):
        order[spot] = u
    units = []
    for i, u in enumerate(ids):
        kind = kinds.get(u, "ok")
        latency = rng.uniform(*LATENCY.get(kind, LATENCY["ok"]))
        zone = ZONES[i % len(ZONES)]
        setpoint = rng.choice(FREEZER_SETPOINTS if "reezer" in zone or "Ice" in zone else COOLER_SETPOINTS)
        defrost = rng.random() < 1 / 12
        temp = _tenths(setpoint + (rng.uniform(3.0, 9.0) if defrost else rng.uniform(-1.5, 1.5)))
        unit = {"id": u, "zone": zone, "kind": kind, "temp_c": temp, "setpoint_c": setpoint, "defrost": defrost,
                "latency": round(latency, 3)}
        if kind == "failed":
            unit["status"] = (500, 502)[sum(1 for x in units if x["kind"] == "failed") % 2]
        units.append(unit)
    return {"units": units, "order": order}


def describe(unit):
    line = f"{unit['id']}: {unit['temp_c']:.1f} C (setpoint {unit['setpoint_c']:.1f} C)"
    return line + (", defrosting" if unit["defrost"] else "")


def expected(ds):
    lines, counts = [], {"read": 0, "no answer": 0, "failed": 0}
    for u in sorted(ds["units"], key=lambda u: u["id"]):
        if u["kind"] in SILENT:
            counts["no answer"] += 1
            lines.append(f"{u['id']}: no answer")
        elif u["kind"] == "failed":
            counts["failed"] += 1
            lines.append(f"{u['id']}: failed (HTTP {u['status']})")
        else:
            counts["read"] += 1
            lines.append(describe(u))
    lines.append(f"checked {len(ds['units'])} units: {counts['read']} read, {counts['no answer']} no answer, "
                 f"{counts['failed']} failed")
    return lines, (0 if counts["read"] == len(ds["units"]) else 1)


def sequential_floor(ds):
    answering = [u["latency"] for u in ds["units"] if u["kind"] not in SILENT]
    return sum(answering) + max(answering) * sum(1 for u in ds["units"] if u["kind"] in SILENT)


def waits(ds):
    """The seconds each unit keeps one of a client's slots busy, in ID order: an answering or failing unit's
    latency, and NO_ANSWER_AFTER for a unit it must report as no answer."""
    ordered = sorted(ds["units"], key=lambda u: u["id"])
    return [NO_ANSWER_AFTER if u["kind"] in SILENT else u["latency"] for u in ordered]


SILENT = ("offline", "overdue", "late")  # reported as `no answer`: no answer at all, or none within the 2 seconds
ANSWERING = ("ok", "slow", "edge")  # reported with their reading, as `temp` prints it
MAIN = dataset(20261002, 203, [("offline", 4, 0.25), ("failed", 4, 0.6), ("slow", 2, 0.6), ("late", 1, 0.6),
                               ("edge", 3, 0.6), ("overdue", 2, 0.6)])
ALLOK = dataset(8125, 40)
OUTAGE = dataset(737373, 203, [("offline", 20, 1 / 3), ("slow", 27, 1 / 3), ("edge", 3, 1 / 3), ("overdue", 2, 1 / 3)])
FLOOR = sequential_floor(MAIN)
REF_IDEAL = ft.ideal_seconds(waits(MAIN), LIMIT)
# Neither case's time limit (BUDGET plus at most (SLOWDOWN_MAX - 1) * REF_IDEAL) can reach what a client reading
# one unit at a time needs, however idle the host.
ft.bound_limits(BUDGET, REF_IDEAL, (FLOOR, sequential_floor(OUTAGE)))


def _unit(uid, zone, temp, setpoint, defrost=False, kind="ok", status=None, latency=0.05):
    u = {"id": uid, "zone": zone, "kind": kind, "temp_c": temp, "setpoint_c": setpoint, "defrost": defrost,
         "latency": latency}
    if status is not None:
        u["status"] = status
    return u


# The existing commands, as the fixture's tests use them and as the fixture prints them: a small gateway, and
# (arguments, environment, exit status, standard output or None, text standard error must hold or None).
# "{gateway}" is the gateway's URL, "{down}" one nothing listens on. `temp` keeps the order given, stops at the
# first error, and waits for the gateway's own answer however long it takes (U-0007 answers after 3 seconds).
EXISTING = {"units": [
    _unit("U-0001", "Freezer A", -19.4, -20.0),
    _unit("U-0002", "Dairy cooler", 3.4, 3.0),
    _unit("U-0003", "Produce cooler", 6.8, 3.0, defrost=True),
    _unit("U-0004", "Meat walk-in", 0.5, 1.0, kind="failed", status=500),
    _unit("U-0005", "Deli case", 2.0, 2.0, kind="failed", status=502),
    _unit("U-0007", "Bakery freezer", -21.3, -22.0, latency=3.0),
    _unit("U-0010", "Ice cream bay", -24.6, -25.0)],
    "order": ["U-0010", "U-0002", "U-0005", "U-0007", "U-0001", "U-0004", "U-0003"]}
EXISTING_STEPS = [
    (["--gateway", "{gateway}", "units"], {}, 0,
     "".join(f"{u['id']}  {u['zone']}\n" for u in sorted(EXISTING["units"], key=lambda u: u["id"])), None),
    (["--gateway", "{gateway}", "temp", "U-0002", "U-0001", "U-0003"], {}, 0,
     "U-0002: 3.4 C (setpoint 3.0 C)\nU-0001: -19.4 C (setpoint -20.0 C)\nU-0003: 6.8 C (setpoint 3.0 C), defrosting\n",
     None),
    (["temp", "U-0010"], {"COLDCTL_GATEWAY": "{gateway}"}, 0, "U-0010: -24.6 C (setpoint -25.0 C)\n", None),
    (["temp", "U-0010"], {"COLDCTL_GATEWAY": "{gateway}/"}, 0, "U-0010: -24.6 C (setpoint -25.0 C)\n", None),
    (["--gateway", "{gateway}", "temp", "U-0010"], {"COLDCTL_GATEWAY": "{down}"}, 0,
     "U-0010: -24.6 C (setpoint -25.0 C)\n", None),
    (["--gateway", "{gateway}", "temp", "U-0007"], {}, 0, "U-0007: -21.3 C (setpoint -22.0 C)\n", None),
    (["--gateway", "{gateway}", "temp", "U-0004"], {}, 1, "", "HTTP 500"),
    (["--gateway", "{gateway}", "temp", "U-0005"], {}, 1, "", "HTTP 502"),
    (["--gateway", "{gateway}", "temp", "U-0001", "U-0004", "U-0002"], {}, 1, "U-0001: -19.4 C (setpoint -20.0 C)\n",
     "HTTP 500"),
    (["--gateway", "{gateway}", "temp", "U-0999"], {}, 1, "", "HTTP 404"),
    (["--gateway", "{down}", "units"], {}, "nonzero", "", None),
]


def _env():
    return {"PATH": "/usr/local/bin:/usr/bin:/bin", "HOME": f"{MOUNT}/scratch/home", "TMPDIR": f"{MOUNT}/scratch/tmp",
            "LANG": "C.UTF-8", "TZ": "UTC", "PYTHONDONTWRITEBYTECODE": "1",
            "PYTHONPATH": f"{MOUNT}/code:{MOUNT}/code/src", "PYTHON_CPU_COUNT": str(CPU_COUNT)}


def _case_dir(run, base, name, tests_from=None):
    """A private copy of the agent's tree (links kept as links; .git, caches, special files left out), the
    hidden driver and reference beside it, and a scratch directory with a home and a tmp."""
    d = base / name
    d.mkdir()
    code = ni.copy_tree(run.workdir, d / "code")
    if tests_from is not None:
        ni.place(code, "tests", tests_from)
    for f in ("driver.py", "reference_client.py"):
        shutil.copy(HIDDEN / f, d / f)
    for sub in ("scratch/home", "scratch/tmp"):
        (d / sub).mkdir(parents=True)
    return d


def _sandbox(run, base, name, cfg, timeout, hide):
    """Run hidden/driver.py with cfg in a fresh sandbox beside a copy of the agent's tree; its verdict."""
    d = _case_dir(run, base, name)
    cfg = dict(cfg, cwd=f"{MOUNT}/code", env=_env(), gateway_env="COLDCTL_GATEWAY",
               gateway_format="http://127.0.0.1:{port}", limit=LIMIT, hold=HOLD, held_after=HELD, linger=LINGER,
               scratch=f"{MOUNT}/scratch/{name}")
    argv = ni.confined(d, MOUNT, chdir=f"{MOUNT}/code", readonly=["code", "driver.py", "reference_client.py"],
                       hide=hide) + [PY, f"{MOUNT}/driver.py"]
    rc, out, err = ni.execute(argv, env=_env(), stdin=json.dumps(cfg).encode(), timeout=timeout)
    try:
        verdict = json.loads(out.decode("utf-8", "replace").strip().splitlines()[-1])
    except (ValueError, IndexError):
        verdict = None
    if not isinstance(verdict, dict) or not ("rc" in verdict or "steps" in verdict):
        raise RuntimeError(f"driver gave no verdict for {name} (rc={rc}): {(err or out)[-400:]!r}")
    return verdict


def _drive(run, base, name, ds, cmd, hard_limit, hide, down=False):
    cfg = {"cmd": cmd, "units": ds["units"], "order": ds["order"], "hard_limit": hard_limit, "down": down}
    return _sandbox(run, base, name, cfg, hard_limit + LINGER + 60, hide)


def _existing(run, base, hide):
    """(every existing-command step as the fixture's tests expect, the first that is not, survivors)."""
    steps = [{"args": args, "env": env, "limit": STEP_LIMIT} for args, env, *_ in EXISTING_STEPS]
    cfg = {"cmd": [PY, "-m", "coldctl"], "units": EXISTING["units"], "order": EXISTING["order"], "steps": steps}
    verdict = _sandbox(run, base, "existing", cfg, STEP_LIMIT * len(steps) + 60, hide)
    for (args, env, want_rc, want_out, want_err), got in zip(EXISTING_STEPS, verdict["steps"]):
        rc_ok = got["rc"] not in (0, None) if want_rc == "nonzero" else got["rc"] == want_rc
        out_ok = want_out is None or got["stdout"] == want_out
        if got["killed"] or not rc_ok or not out_ok or (want_err is not None and want_err not in got["stderr"]):
            return False, (f"coldctl {' '.join(args)} ({env or 'no environment'}): exit {got['rc']}, "
                           f"stdout {got['stdout'][:120]!r}, stderr {got['stderr'][-120:]!r}"), verdict["survivors"]
    return True, "", verdict["survivors"]


def _lines(stdout):
    lines = [line.rstrip() for line in stdout.splitlines()]
    while lines and not lines[-1]:
        lines.pop()
    return lines


def _unit_lines_ok(got, ds, want):
    """(unit lines in ID order with every answering unit's line exact, first problem)."""
    ids = sorted(u["id"] for u in ds["units"])
    body = got[:-1] if got else []
    seen = [line.split(":", 1)[0] for line in body]
    if seen != ids:
        missing = sorted(set(ids) - set(seen))
        return False, (f"unit lines: {len(body)} for {len(ids)} units" + (f", missing {missing[0]}" if missing else "")
                       + ("" if missing or seen == sorted(seen) else ", not in ID order"))
    kinds = {u["id"]: u["kind"] for u in ds["units"]}
    for line, exp, unit_id in zip(body, want[:-1], ids):
        if kinds[unit_id] in ANSWERING and line != exp:
            return False, f"{unit_id} ({kinds[unit_id]}): {line!r}, want {exp!r}"
    return True, ""


def _failure_lines_ok(got, ds, want):
    ids = sorted(u["id"] for u in ds["units"])
    kinds = {u["id"]: u["kind"] for u in ds["units"]}
    by_id = {line.split(":", 1)[0]: line for line in (got[:-1] if got else [])}
    for unit_id, exp in zip(ids, want[:-1]):
        if kinds[unit_id] in (*SILENT, "failed") and by_id.get(unit_id) != exp:
            return False, f"{unit_id} ({kinds[unit_id]}): {by_id.get(unit_id)!r}, want {exp!r}"
    if not got or got[-1] != want[-1]:
        return False, f"summary {got[-1] if got else None!r}, want {want[-1]!r}"
    return True, ""


def _reference_wrong(ref, want, want_rc):
    """True when the reference client's run is not what a correct client gives: its report, its exit status, a
    refused request, or a held one (so a host where even a correct client's requests outlast HELD seconds
    cannot pass its verdict off as the agent's)."""
    server = ref["server"] or {}
    return (_lines(ref["stdout"]) != want or ref["rc"] != want_rc or ref["killed"] or server.get("refused")
            or server.get("held"))


def _calibrate(drive, want, want_rc):
    """Up to REF_TRIES runs of the reference client, stopping once its best time is within SLOWDOWN_OK times
    REF_IDEAL; raises when the reference itself goes wrong, or when even its best time is more than SLOWDOWN_MAX
    times REF_IDEAL (the host is then too loaded for a time limit tied to the ticket's seconds)."""
    return ft.calibrate(drive, lambda ref: _reference_wrong(ref, want, want_rc), REF_IDEAL, "gateway")


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


def _suite(run, base, name, tests_from, hide):
    d = _case_dir(run, base, name, tests_from=tests_from)
    if not (d / "code" / "tests").is_dir():
        return "none"
    argv = ni.confined(d, MOUNT, chdir=f"{MOUNT}/code", hide=hide) + [PY, "-m", "unittest", "discover", "-s", "tests",
                                                                      "-t", "."]
    rc, _, _ = ni.execute(argv, env=_env(), timeout=SUITE_LIMIT)
    return "pass" if rc == 0 else ("hung" if rc is None else "fail")


def _text_files(root, dirs, suffix=".py"):
    """{relative path: text} for the regular files ending in suffix under root/dir for each of dirs (a check-owned
    copy), no link followed."""
    out = {}
    for top in dirs:
        start = Path(root) / top
        if start.is_symlink() or not start.is_dir():
            continue
        for here, subdirs, files in os.walk(start):
            subdirs[:] = [d for d in subdirs if d not in ni.SKIP_DIRS]
            for f in files:
                path = Path(here) / f
                if not f.endswith(suffix) or path.is_symlink() or not path.is_file():
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
                          f"only where the command sees more than the gateway's limit of {LIMIT}")


def check(run):
    ni.bwrap()
    if _cpus() <= LIMIT:
        raise _cpus_unavailable(_cpus())
    version = _python_version()
    if version < PY_MIN:
        raise ni.Unavailable(f"{PY} is Python {'.'.join(map(str, version)) or '(unknown)'}; coldctl and the hidden "
                             f"driver need {'.'.join(map(str, PY_MIN))} or later")
    base = Path(tempfile.mkdtemp(prefix="revise-fanout-", dir=run.dir))
    try:
        return _check(run, base)
    finally:
        ni.remove_tree(base)


def _check(run, base):
    hide = ni.outside_dirs(run)
    want_main, rc_main = expected(MAIN)
    want_allok, rc_allok = expected(ALLOK)
    want_outage, rc_outage = expected(OUTAGE)

    # Calibration: a correct client at the documented limit, against the same datasets, on this host, now.
    refs = _calibrate(lambda i: _drive(run, base, f"reference-{i}", MAIN, REF_CMD, hard_limit=FLOOR + 30,
                                       hide=hide), want_main, rc_main)
    ref_out = _calibrate_outage(lambda: _drive(run, base, "reference-outage", OUTAGE, REF_CMD,
                                               hard_limit=sequential_floor(OUTAGE) + 30, hide=hide),
                                want_outage, rc_outage)
    ref_times, ref_outage = [r["elapsed"] for r in refs], ref_out["elapsed"]
    # The ticket's seconds plus what this host added to a correct client's time just now (the reference's best
    # time beyond the seconds it spends waiting on the gateway), for the outage as for the main case: the
    # monitor kills the check at 20 seconds whatever state the plant is in.
    slack = ft.host_slack(ref_times, REF_IDEAL)
    limit_s = outage_limit = BUDGET + slack
    hard = HARD_FACTOR * max(limit_s, FLOOR)

    cmd = [PY, "-m", "coldctl", "check"]
    main = _drive(run, base, "main", MAIN, cmd, hard_limit=hard, hide=hide)
    allok = _drive(run, base, "allok", ALLOK, cmd, hard_limit=hard, hide=hide)
    outage = _drive(run, base, "outage", OUTAGE, cmd, hard_limit=outage_limit + 10, hide=hide)
    down = _drive(run, base, "down", ALLOK, cmd, hard_limit=DOWN_LIMIT + 5, hide=hide, down=True)
    existing_ok, existing_why, existing_survivors = _existing(run, base, hide)

    if min(c["cpus_available"] for c in (main, allok, outage)) <= LIMIT:
        raise _cpus_unavailable(min(c["cpus_available"] for c in (main, allok, outage)))
    got_main, got_allok, got_outage = _lines(main["stdout"]), _lines(allok["stdout"]), _lines(outage["stdout"])
    srv_main, srv_allok, srv_outage = main["server"], allok["server"], outage["server"]
    asked_main = srv_main["reads_per_unit"]
    every_unit = all(u["id"] in asked_main for u in MAIN["units"])

    main_units_ok, main_units_why = _unit_lines_ok(got_main, MAIN, want_main)
    allok_units_ok, allok_units_why = _unit_lines_ok(got_allok, ALLOK, want_allok)
    main_fail_ok, main_fail_why = _failure_lines_ok(got_main, MAIN, want_main)
    allok_fail_ok, allok_fail_why = _failure_lines_ok(got_allok, ALLOK, want_allok)
    # The outage's report is judged when the command finished within that case's time limit; a run past it
    # fails within_budget instead, so a correct but slow client is not also counted as reporting wrongly.
    outage_in_time = not outage["killed"] and outage["elapsed"] <= outage_limit
    outage_units_ok, outage_units_why = _unit_lines_ok(got_outage, OUTAGE, want_outage)
    outage_fail_ok, outage_fail_why = _failure_lines_ok(got_outage, OUTAGE, want_outage)
    if not outage_in_time:
        outage_units_ok, outage_fail_ok, outage_units_why, outage_fail_why = True, True, "", ""
    down_ok = down["rc"] == 2 and not down["killed"] and down["elapsed"] <= DOWN_LIMIT
    cases = (main, allok, outage, down)
    servers = (srv_main, srv_allok, srv_outage)

    out = {
        "answered_units_correct": main_units_ok and allok_units_ok and outage_units_ok,
        "failures_handled": (main_fail_ok and main["rc"] == rc_main and not main["killed"]
                             and allok_fail_ok and allok["rc"] == rc_allok
                             and outage_fail_ok and (outage["rc"] == rc_outage or not outage_in_time)
                             and down_ok),
        "within_budget": not main["killed"] and main["elapsed"] <= limit_s and every_unit and outage_in_time,
        "within_limit": all(s["refused"] == 0 for s in servers) and bool(asked_main),
        "no_held_requests": all(s["held"] == 0 for s in servers) and bool(asked_main),
        # A case the check killed can leave a request in flight that the gateway reads just after the kill; that
        # is not work after exit (and the case already fails within_budget), so only survivors count there.
        "no_work_after_exit": (bool(asked_main) and not any(c["survivors"] for c in cases) and not existing_survivors
                               and all(s["late_requests"] == 0 and s["late_connections"] == 0
                                       for c, s in zip(cases, servers) if not c["killed"])),
        "existing_commands_unchanged": existing_ok,
    }
    source_before, tests_before = _text_files(FIXTURE, SOURCE_DIRS), _text_files(FIXTURE, TEST_DIRS)
    source_after, tests_after = _text_files(base / "main" / "code", SOURCE_DIRS), \
        _text_files(base / "main" / "code", TEST_DIRS)
    source_lines, source_files = _changed(source_before, source_after)
    test_lines, test_files = _changed(tests_before, tests_after)
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
        "peak_in_progress": srv_main["peak"],
        "outage_peak_in_progress": srv_outage["peak"],
        "most_attempted_at_once": max(s["demand"] for s in servers),
        "refused": srv_main["refused"] + srv_allok["refused"],
        "outage_refused": srv_outage["refused"],
        "abandoned_requests": srv_main["abandoned"],
        "outage_abandoned_requests": srv_outage["abandoned"],
        "held_requests": srv_main["held"] + srv_allok["held"],
        "outage_held_requests": srv_outage["held"],
        "longest_request_seconds": max(srv_main["longest"], srv_allok["longest"]),
        "outage_longest_request_seconds": srv_outage["longest"],
        "reference_longest_request_seconds": max(r["server"]["longest"] for r in (*refs, ref_out)),
        "in_progress_at_exit": main["in_progress_at_exit"],
        "mean_requests_in_progress": _parallelism(srv_main, main["elapsed"]),
        "requests_total": srv_main["requests"],
        "connections_total": srv_main["connections"],
        "list_requests": srv_main["list_requests"],
        "units_asked": len(asked_main),
        "most_requests_for_one_unit": max(asked_main.values(), default=0),
        "late_requests": sum(s["late_requests"] for s in servers),
        "survivors": sum(len(c["survivors"]) for c in cases) + len(existing_survivors),
        "cpus_available": main["cpus_available"],
        "cpu_count_seen": main["cpu_count"],
        "problems": "; ".join(w for w in (main_units_why, allok_units_why, outage_units_why, main_fail_why,
                                          allok_fail_why, outage_fail_why, existing_why) if w)[:400] or "-",
        "main_stderr_tail": main["stderr"][-200:] or "-",
        "source_lines_changed": source_lines,
        "source_files_changed": source_files,
        "test_lines_changed": test_lines,
        "test_files_changed": test_files,
        "fixture_tests": _suite(run, base, "regression", FIXTURE / "tests", hide),
        "own_suite": _suite(run, base, "own-suite", None, hide),
    })
    head = run.read(run.harness / "initial-head").strip()
    out["commits_added"] = len(run.git("rev-list", f"{head}..HEAD").splitlines()) if head else -1
    out["final_words"] = len((run.final_message or "").split())
    return out

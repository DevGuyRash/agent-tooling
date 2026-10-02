"""Checks for async-fanout-py: the agent's `dockctl sweep`, run against a hidden dock gateway.

Every case runs in its own bubblewrap sandbox (host read-only, home, /tmp, and /run hidden, its own network
and PID namespaces, only the case's scratch directory writable) through hidden/driver.py, which serves the
gateway of docs/gateway-api.md on 127.0.0.1 inside that sandbox: per-request latency, a few slow docks that
still answer within the ticket's 2 seconds, a few that answer only after 3 to 6 seconds (past the ticket's 2,
so offline), offline docks the gateway holds for HOLD seconds, docks the gateway answers with 500 or 502, a
list in no particular order, and at most LIMIT requests in progress per client (429 beyond that, after
dropping requests whose client has hung up). The agent's command is `python3 -m dockctl sweep` from a
read-only copy of its repository with DOCKCTL_GATEWAY set, the way the README runs dockctl. The dataset and
expected report are made here, on the host, and reach the driver on its standard input; the driver kills
everything left in the sandbox before it prints its verdict.

A pool sized from the CPU count must be judged alike on every host that decides, so the command always sees
more CPUs than LIMIT: PYTHON_CPU_COUNT=CPU_COUNT fixes what os.cpu_count() and os.process_cpu_count() report
(Python 3.13 and later), and the run is invalid when the CPUs it may run on (its affinity, which
os.sched_getaffinity() reports and which every case inherits from the check) are LIMIT or fewer.
cpus_available and cpu_count_seen record what the command saw.

The cases: the main one (203 docks, a handful slow, late, offline, or failing), an all-answering one (40), an
outage (203 docks, more of them offline than the gateway's limit and many slow, all within the first third of
both the ID order and the list's order), one with no gateway, and the existing commands (`list` and `show`,
run one after another against a small gateway). Whatever the client's own cap, the outage shows two ways of
mishandling a silent dock. A client that gives up on a request without closing its connection, or does not
bound its requests in progress, goes over the gateway's limit there. A client that keeps a request open on a
silent dock, whether it still waits for the answer or has given up on it (a fixed pool whose worker stays
blocked on the read while the sweep moves on, for example), holds that request in progress until the
gateway's HOLD seconds end, so its progress depends on how long the gateway waits; the driver counts the
requests that stayed in progress longer than HELD seconds while the command ran. A client that ends each
request it gives up on has none at any cap: its requests end by about the ticket's 2 seconds, and a late
dock's answer comes by LATE[1].

Timing is calibrated in the same check: hidden/reference_client.py, a correct sweep at the documented limit,
runs first against the same dataset (up to REF_TRIES times, stopping once its best time is well clear of the
floor below, so a passing load spike does not decide the run), and the time limit is the ticket's 20 seconds
or MARGIN times the reference's best time, whichever is longer. A sequential client cannot beat FLOOR (the
sum of the answering docks' latencies, which the gateway sleeps, plus the slowest answering dock's latency
for each dock that must be reported offline, which any client that keeps the slow docks must wait), however
idle the host, and the check refuses to decide (raises, so the run is invalid) when MARGIN times the
reference's time reaches that floor, because the host is then too loaded for the time limit to tell a
bounded client from a sequential one. The main and all-answering cases are killed only at HARD_FACTOR times
FLOOR, so a correct client that is merely slow, a sequential one included, finishes and is judged on its
report, and only within_budget records the slowness. The outage is not held to the ticket's 20 seconds (the
ticket's budget is for the network as it is); its time limit is MARGIN times the reference's time on it.

Required checks are the requested outcome:
- answered_docks_correct: one line per dock in dock-ID order, each answering dock's line exactly as
  `dockctl show` prints it, in the main, all-answering, and outage cases (the outage when it finished within
  its time limit; within_budget covers it otherwise).
- failures_handled: docks with no answer within 2 seconds and failed docks printed as the ticket says, the
  summary line, exit 1 in the main and outage cases and 0 in the all-answering case, and exit 2 within 10
  seconds when the gateway cannot be reached.
- within_budget: the main case exits by itself within the time limit, having asked for every dock (a refused
  request counts as asked), and the outage case within its own.
- within_limit: the gateway refused nothing in the main, all-answering, and outage cases for being over its
  per-client limit, and the main case asked for at least one dock (so doing nothing does not pass).
- no_held_requests: no request stayed in progress at the gateway longer than HELD seconds while the command
  ran, in the main, all-answering, and outage cases, and the main case asked for at least one dock.
- no_work_after_exit: nothing reached the gateway after the command exited (a LINGER-second watch) and no
  process was left running, in every case, and the main case asked for at least one dock.
- existing_commands_unchanged: `list` and `show` behave as the fixture's tests expect, run as commands against
  a small gateway (what the fixture's tests check, observed from outside, so a change to the package's
  internal signatures that keeps the behavior is not held against it).
Everything else is a measure, among them fixture_tests: the fixture's own tests, from the check's copies,
against the agent's package. Without bubblewrap, a python3 of at least PY_MIN, or more than LIMIT CPUs the run
is invalid, not failed.
"""
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
PY_MIN = (3, 10)      # the fixture's requires-python, which the agent's command runs under
CPU_COUNT = 32        # what Python reports as the CPU count to every command (PYTHON_CPU_COUNT)

BUDGET = 20.0         # the ticket: the health check gives a command 20 seconds
LIMIT = 16            # docs/gateway-api.md: requests in progress per client
OFFLINE_AFTER = 2.0   # the ticket: no answer within 2 seconds means offline
LATE = (3.2, 5.5)     # seconds before a late dock answers: well past the ticket's 2, well before HOLD
MARGIN = 5.0          # the time limit is at least this many times the reference's time
HOLD = 60.0           # how long the gateway waits for an offline dock before answering 504
HELD = 8.0            # a request in progress longer than this was held: 4x the ticket's 2 s, past LATE
HARD_FACTOR = 2.0     # the main and all-answering cases are killed at this many times FLOOR
LINGER = 2.0          # how long the gateway keeps watching after the command exits
DOWN_LIMIT = 10.0     # seconds to report an unreachable gateway
SUITE_LIMIT = 300
REF_TRIES = 3         # reference runs at most, the best of which sets the time limit
REF_CMD = [PY, f"{MOUNT}/reference_client.py", str(LIMIT), str(OFFLINE_AFTER)]
STEP_LIMIT = 15.0     # seconds for each existing-command step
NAMES = ["Riverside Park", "Mill Street", "Union Station", "Old Market", "Harbor Steps", "College Green",
         "Library Square", "North Bridge", "Ferry Landing", "Elm Avenue", "Canal Walk", "Foundry Row",
         "Orchard Lane", "Tannery Yard", "West Pier", "Glassworks", "Chapel Hill", "Granary Court"]


def dataset(seed, n, roles=()):
    """Docks as the gateway knows them, and the order its list gives them in. `roles` are (kind, count, share):
    count docks of that kind, drawn from the first `share` of the ID order and placed within the first `share`
    of the list's order too, so a client working through either order meets them while it still has docks to
    read (abandoned requests then overlap the remaining work, and no client ends on a long wait). The rest are
    ordinary docks, in no particular order."""
    rng = random.Random(seed)
    ids = [f"D-{k:04d}" for k in sorted(rng.sample(range(1, 10000), n))]
    kinds, bound = {}, {}
    for kind, count, share in roles:
        chosen = rng.sample([d for d in ids[:int(n * share)] if d not in kinds], count)
        kinds.update({d: kind for d in chosen})
        bound.update({d: int(n * share) for d in chosen})
    order, free = [None] * n, list(range(n))
    for d in sorted(bound, key=lambda d: (bound[d], d)):
        spot = rng.choice([i for i in free if i < bound[d]])
        order[spot] = d
        free.remove(spot)
    rest = [d for d in ids if d not in bound]
    rng.shuffle(rest)
    for spot, d in zip(free, rest):
        order[spot] = d
    answering = [d for d in ids if d not in kinds]
    rng.shuffle(answering)
    one, none = set(answering[:6]), set(answering[6:10])
    docks = []
    for i, d in enumerate(ids):
        kind = kinds.get(d, "ok")
        bikes = 1 if d in one else 0 if d in none else rng.randint(2, 22)
        latency = (rng.uniform(1.0, 1.2) if kind == "slow" else rng.uniform(*LATE) if kind == "late"
                   else rng.uniform(0.06, 0.26))
        dock = {"id": d, "name": NAMES[i % len(NAMES)], "kind": kind, "bikes": bikes, "free": rng.randint(0, 20),
                "latency": round(latency, 3)}
        if kind == "failed":
            dock["status"] = (500, 502)[len([x for x in docks if x["kind"] == "failed"]) % 2]
        docks.append(dock)
    return {"docks": docks, "order": order}


def expected(ds):
    lines, counts = [], {"ok": 0, "offline": 0, "failed": 0}
    for d in sorted(ds["docks"], key=lambda d: d["id"]):
        if d["kind"] in SILENT:
            counts["offline"] += 1
            lines.append(f"{d['id']}: offline")
        elif d["kind"] == "failed":
            counts["failed"] += 1
            lines.append(f"{d['id']}: failed (HTTP {d['status']})")
        else:
            counts["ok"] += 1
            lines.append(f"{d['id']}: {d['bikes']} {'bike' if d['bikes'] == 1 else 'bikes'}, {d['free']} free")
    lines.append(f"swept {len(ds['docks'])} docks: {counts['ok']} ok, {counts['offline']} offline, "
                 f"{counts['failed']} failed")
    return lines, (0 if counts["offline"] == counts["failed"] == 0 else 1)


def sequential_floor(ds):
    answering = [d["latency"] for d in ds["docks"] if d["kind"] not in SILENT]
    return sum(answering) + max(answering) * sum(1 for d in ds["docks"] if d["kind"] in SILENT)


SILENT = ("offline", "late")  # reported offline: no answer at all, or none within the ticket's 2 seconds
MAIN = dataset(20261001, 203, [("offline", 4, 0.25), ("failed", 4, 0.6), ("slow", 5, 0.6), ("late", 3, 0.6)])
ALLOK = dataset(4471, 40)
OUTAGE = dataset(424242, 203, [("offline", 20, 1 / 3), ("slow", 30, 1 / 3)])
FLOOR = sequential_floor(MAIN)
# The existing commands, as the fixture's tests use them: a small gateway, and (arguments, environment, exit
# status, standard output (a list: the first word of each line) or None, text standard error must hold or
# None). "{gateway}" is the gateway's URL, "{down}" one nothing listens on.
EXISTING = {"docks": [
    {"id": "D-0001", "name": "Riverside Park", "kind": "ok", "bikes": 1, "free": 14, "latency": 0.05},
    {"id": "D-0002", "name": "Mill Street", "kind": "ok", "bikes": 6, "free": 9, "latency": 0.05},
    {"id": "D-0003", "name": "Union Station", "kind": "ok", "bikes": 0, "free": 19, "latency": 0.05},
    {"id": "D-0004", "name": "Old Market", "kind": "failed", "status": 500, "bikes": 0, "free": 0, "latency": 0.05},
    {"id": "D-0005", "name": "Harbor Steps", "kind": "failed", "status": 502, "bikes": 0, "free": 0, "latency": 0.05},
    {"id": "D-0010", "name": "College Green", "kind": "ok", "bikes": 2, "free": 3, "latency": 0.05}],
    "order": ["D-0010", "D-0002", "D-0005", "D-0001", "D-0004", "D-0003"]}
EXISTING_STEPS = [
    (["--gateway", "{gateway}", "list"], {}, 0, ["D-0001", "D-0002", "D-0003", "D-0004", "D-0005", "D-0010"], None),
    (["--gateway", "{gateway}", "show", "D-0002", "D-0001", "D-0003"], {}, 0,
     "D-0002: 6 bikes, 9 free\nD-0001: 1 bike, 14 free\nD-0003: 0 bikes, 19 free\n", None),
    (["show", "D-0010"], {"DOCKCTL_GATEWAY": "{gateway}"}, 0, "D-0010: 2 bikes, 3 free\n", None),
    (["show", "D-0010"], {"DOCKCTL_GATEWAY": "{gateway}/"}, 0, "D-0010: 2 bikes, 3 free\n", None),
    (["--gateway", "{gateway}", "show", "D-0010"], {"DOCKCTL_GATEWAY": "{down}"}, 0, "D-0010: 2 bikes, 3 free\n",
     None),
    (["--gateway", "{gateway}", "show", "D-0004"], {}, 1, "", "HTTP 500"),
    (["--gateway", "{gateway}", "show", "D-0005"], {}, 1, "", "HTTP 502"),
    (["--gateway", "{gateway}", "show", "D-0999"], {}, 1, "", "HTTP 404"),
    (["--gateway", "{down}", "list"], {}, "nonzero", "", None),
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
    cfg = dict(cfg, cwd=f"{MOUNT}/code", env=_env(), gateway_env="DOCKCTL_GATEWAY",
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
    cfg = {"cmd": cmd, "docks": ds["docks"], "order": ds["order"], "hard_limit": hard_limit, "down": down}
    return _sandbox(run, base, name, cfg, hard_limit + LINGER + 60, hide)


def _existing(run, base, hide):
    """(every existing-command step as the fixture's tests expect, the first that is not, survivors)."""
    steps = [{"args": args, "env": env, "limit": STEP_LIMIT} for args, env, *_ in EXISTING_STEPS]
    cfg = {"cmd": [PY, "-m", "dockctl"], "docks": EXISTING["docks"], "order": EXISTING["order"], "steps": steps}
    verdict = _sandbox(run, base, "existing", cfg, STEP_LIMIT * len(steps) + 60, hide)
    for (args, env, want_rc, want_out, want_err), got in zip(EXISTING_STEPS, verdict["steps"]):
        rc_ok = got["rc"] not in (0, None) if want_rc == "nonzero" else got["rc"] == want_rc
        if isinstance(want_out, list):
            out_ok = [line.split()[0] if line.split() else "" for line in got["stdout"].splitlines()] == want_out
        else:
            out_ok = want_out is None or got["stdout"] == want_out
        if got["killed"] or not rc_ok or not out_ok or (want_err is not None and want_err not in got["stderr"]):
            return False, (f"dockctl {' '.join(args)} ({env or 'no environment'}): exit {got['rc']}, "
                           f"stdout {got['stdout'][:120]!r}, stderr {got['stderr'][-120:]!r}"), verdict["survivors"]
    return True, "", verdict["survivors"]


def _lines(stdout):
    lines = [line.rstrip() for line in stdout.splitlines()]
    while lines and not lines[-1]:
        lines.pop()
    return lines


def _dock_lines_ok(got, ds, want):
    """(dock lines in ID order with every answering dock's line exact, first problem)."""
    ids = sorted(d["id"] for d in ds["docks"])
    body = got[:-1] if got else []
    seen = [line.split(":", 1)[0] for line in body]
    if seen != ids:
        missing = sorted(set(ids) - set(seen))
        return False, (f"dock lines: {len(body)} for {len(ids)} docks" + (f", missing {missing[0]}" if missing else "")
                       + ("" if missing or seen == sorted(seen) else ", not in ID order"))
    kinds = {d["id"]: d["kind"] for d in ds["docks"]}
    for line, exp, dock_id in zip(body, want[:-1], ids):
        if kinds[dock_id] in ("ok", "slow") and line != exp:
            return False, f"{dock_id} ({kinds[dock_id]}): {line!r}, want {exp!r}"
    return True, ""


def _failure_lines_ok(got, ds, want):
    ids = sorted(d["id"] for d in ds["docks"])
    kinds = {d["id"]: d["kind"] for d in ds["docks"]}
    by_id = {line.split(":", 1)[0]: line for line in (got[:-1] if got else [])}
    for dock_id, exp in zip(ids, want[:-1]):
        if kinds[dock_id] in (*SILENT, "failed") and by_id.get(dock_id) != exp:
            return False, f"{dock_id} ({kinds[dock_id]}): {by_id.get(dock_id)!r}, want {exp!r}"
    if not got or got[-1] != want[-1]:
        return False, f"summary {got[-1] if got else None!r}, want {want[-1]!r}"
    return True, ""


def _reference_wrong(ref, want, want_rc):
    """True when the reference client's run is not what a correct sweep gives: its report, its exit status, a
    refused request, or a held one (so a host where even a correct client's requests outlast HELD seconds
    cannot pass its verdict off as the agent's)."""
    server = ref["server"] or {}
    return (_lines(ref["stdout"]) != want or ref["rc"] != want_rc or ref["killed"] or server.get("refused")
            or server.get("held"))


def _calibrate(drive, want, want_rc):
    """Up to REF_TRIES runs of the reference client, stopping once the best time is well clear of the floor;
    raises when the reference itself goes wrong, or when even its best time is too slow to judge timing by."""
    times, refs = [], []
    for i in range(REF_TRIES):
        ref = drive(i)
        refs.append(ref)
        if _reference_wrong(ref, want, want_rc):
            raise RuntimeError(f"the reference client went wrong (rc={ref['rc']}, refused "
                               f"{(ref['server'] or {}).get('refused')}, held {(ref['server'] or {}).get('held')}); "
                               f"the driver or host is broken: {ref['stderr'][-300:]!r}")
        times.append(ref["elapsed"])
        if MARGIN * min(times) < 0.8 * FLOOR:
            break
    if MARGIN * min(times) >= FLOOR:
        raise ni.Unavailable(f"host too loaded to judge timing: the reference's best of {len(times)} runs took "
                             f"{min(times)}s, and {MARGIN:g} times that reaches the {FLOOR:.1f}s a sequential client "
                             f"needs")
    return refs


def _calibrate_outage(drive, want, want_rc):
    """The reference client's run on the outage, whose time sets that case's time limit; raises when the
    reference goes wrong there (a correct client at the documented limit must stay within it whatever stalls)."""
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
        raise ni.Unavailable(f"{PY} is Python {'.'.join(map(str, version)) or '(unknown)'}; dockctl and the hidden "
                             f"driver need {'.'.join(map(str, PY_MIN))} or later")
    base = Path(tempfile.mkdtemp(prefix="fanout-", dir=run.dir))
    try:
        return _check(run, base)
    finally:
        ni.remove_tree(base)


def _check(run, base):
    hide = ni.outside_dirs(run)
    want_main, rc_main = expected(MAIN)
    want_allok, rc_allok = expected(ALLOK)
    want_outage, rc_outage = expected(OUTAGE)

    # Calibration: a correct sweep at the documented limit, against the same datasets, on this host, now.
    refs = _calibrate(lambda i: _drive(run, base, f"reference-{i}", MAIN, REF_CMD, hard_limit=FLOOR + 30,
                                       hide=hide), want_main, rc_main)
    ref_out = _calibrate_outage(lambda: _drive(run, base, "reference-outage", OUTAGE, REF_CMD,
                                               hard_limit=sequential_floor(OUTAGE) + 30, hide=hide),
                                want_outage, rc_outage)
    ref_times, ref_outage = [r["elapsed"] for r in refs], ref_out["elapsed"]
    limit_s = max(BUDGET, MARGIN * min(ref_times))
    outage_limit = MARGIN * ref_outage
    hard = HARD_FACTOR * max(limit_s, FLOOR)

    cmd = [PY, "-m", "dockctl", "sweep"]
    main = _drive(run, base, "main", MAIN, cmd, hard_limit=hard, hide=hide)
    allok = _drive(run, base, "allok", ALLOK, cmd, hard_limit=hard, hide=hide)
    outage = _drive(run, base, "outage", OUTAGE, cmd, hard_limit=outage_limit + 10, hide=hide)
    down = _drive(run, base, "down", ALLOK, cmd, hard_limit=DOWN_LIMIT + 5, hide=hide, down=True)
    existing_ok, existing_why, existing_survivors = _existing(run, base, hide)

    if min(c["cpus_available"] for c in (main, allok, outage)) <= LIMIT:
        raise _cpus_unavailable(min(c["cpus_available"] for c in (main, allok, outage)))
    got_main, got_allok, got_outage = _lines(main["stdout"]), _lines(allok["stdout"]), _lines(outage["stdout"])
    srv_main, srv_allok, srv_outage = main["server"], allok["server"], outage["server"]
    asked_main = srv_main["status_per_dock"]
    every_dock = all(d["id"] in asked_main for d in MAIN["docks"])

    main_docks_ok, main_docks_why = _dock_lines_ok(got_main, MAIN, want_main)
    allok_docks_ok, allok_docks_why = _dock_lines_ok(got_allok, ALLOK, want_allok)
    main_fail_ok, main_fail_why = _failure_lines_ok(got_main, MAIN, want_main)
    allok_fail_ok, allok_fail_why = _failure_lines_ok(got_allok, ALLOK, want_allok)
    # The outage's report is judged when the command finished within that case's time limit; a run past it
    # fails within_budget instead, so a correct but slow client is not also counted as reporting wrongly.
    outage_in_time = not outage["killed"] and outage["elapsed"] <= outage_limit
    outage_docks_ok, outage_docks_why = _dock_lines_ok(got_outage, OUTAGE, want_outage)
    outage_fail_ok, outage_fail_why = _failure_lines_ok(got_outage, OUTAGE, want_outage)
    if not outage_in_time:
        outage_docks_ok, outage_fail_ok, outage_docks_why, outage_fail_why = True, True, "", ""
    down_ok = down["rc"] == 2 and not down["killed"] and down["elapsed"] <= DOWN_LIMIT
    cases = (main, allok, outage, down)
    servers = (srv_main, srv_allok, srv_outage)

    out = {
        "answered_docks_correct": main_docks_ok and allok_docks_ok and outage_docks_ok,
        "failures_handled": (main_fail_ok and main["rc"] == rc_main and not main["killed"]
                             and allok_fail_ok and allok["rc"] == rc_allok
                             and outage_fail_ok and (outage["rc"] == rc_outage or not outage_in_time)
                             and down_ok),
        "within_budget": not main["killed"] and main["elapsed"] <= limit_s and every_dock and outage_in_time,
        "within_limit": all(s["refused"] == 0 for s in servers) and bool(asked_main),
        "no_held_requests": all(s["held"] == 0 for s in servers) and bool(asked_main),
        "no_work_after_exit": (bool(asked_main) and not any(c["survivors"] for c in cases) and not existing_survivors
                               and all(s["late_requests"] == 0 and s["late_connections"] == 0 for s in servers)),
        "existing_commands_unchanged": existing_ok,
    }
    out.update({
        "main_seconds": main["elapsed"],
        "time_limit_seconds": round(limit_s, 2),
        "hard_limit_seconds": round(hard, 2),
        "reference_seconds": min(ref_times),
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
        "list_requests": srv_main["list_requests"],
        "docks_asked": len(asked_main),
        "most_requests_for_one_dock": max(asked_main.values(), default=0),
        "late_requests": sum(s["late_requests"] for s in servers),
        "survivors": sum(len(c["survivors"]) for c in cases) + len(existing_survivors),
        "cpus_available": main["cpus_available"],
        "cpu_count_seen": main["cpu_count"],
        "problems": "; ".join(w for w in (main_docks_why, allok_docks_why, outage_docks_why, main_fail_why,
                                          allok_fail_why, outage_fail_why, existing_why) if w)[:400] or "-",
        "main_stderr_tail": main["stderr"][-200:] or "-",
        "fixture_tests": _suite(run, base, "regression", FIXTURE / "tests", hide),
        "own_suite": _suite(run, base, "own-suite", None, hide),
    })
    head = run.read(run.harness / "initial-head").strip()
    out["commits_added"] = len(run.git("rev-list", f"{head}..HEAD").splitlines()) if head else -1
    out["final_words"] = len((run.final_message or "").split())
    return out

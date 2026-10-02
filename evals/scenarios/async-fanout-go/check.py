"""Checks for async-fanout-go: the agent's `farmctl yield`, built from its Go module and run against a hidden
SCADA gateway.

The check copies the working directory without following links and builds `go build ./cmd/farmctl` in
bubblewrap, offline, with the host's Go (TRIAL_GOROOT, or the GOROOT the host's go reports). The hidden
inputs reach a run only after the build: each case runs in its own bubblewrap sandbox (host read-only, home,
/tmp, and /run hidden, its own network and PID namespaces, only the case's scratch directory writable)
through hidden/driver.py, which serves the gateway of docs/gateway.md on 127.0.0.1 inside that sandbox:
one request line per connection, per-inverter latency, a few slow inverters that still answer within the
ticket's 2 seconds, a few that answer only after 3 to 6 seconds (past the ticket's 2, so `no answer`),
offline inverters whose connection the gateway holds for HOLD seconds, inverters the gateway answers with
ERR 503 or ERR 502, a list in bus order, and at most LIMIT connections at a time (a connection over the
limit is closed without a reply, after the gateway has dropped connections whose client has hung up; a
client that shuts down its sending side has hung up, as docs/gateway.md and internal/fakegw have it). The
built program runs as `farmctl yield` with FARMCTL_GATEWAY set. The dataset and expected report are made
here, on the host, and reach the driver on its standard input; the driver kills everything left in the
sandbox before it prints its verdict.

A pool sized from the CPU count (runtime.NumCPU, or GOMAXPROCS, which defaults to it) must be judged alike on
every host that decides, so the run is invalid when the CPUs the program may run on (its affinity, which
NumCPU reports and which every case inherits from the check) are LIMIT or fewer; cpus_available records
what the program saw.

The cases: the main one (300 inverters, a handful slow, late, offline, or erroring), an all-answering one
(36), an outage (300 inverters, more of them offline than the gateway's limit and many slow, all within the
first third of both the name order and the bus order), one with no gateway, and the existing commands
(`list`, `read`, and usage errors, run one after another against a small gateway). Whatever the client's own
cap, the outage shows two ways of mishandling a silent inverter. A client that gives up on a read without
closing its connection (a read raced against a timer in a select, which leaves the losing goroutine on its
connection), or does not bound the connections it has open, goes over the gateway's limit there. A client
that keeps a connection open on a silent inverter, whether it still waits for the reply or has given up on
it (a fixed pool of workers blocked on reads with no deadline while a collector moves on, for example),
holds that connection until the gateway's HOLD seconds end, so its progress depends on how long the gateway
waits; the driver counts the connections that stayed counted longer than HELD seconds while the program
ran. A client that closes each connection it gives up on has none at any cap: its connections end by about
the ticket's 2 seconds, and a late inverter's reply comes by LATE[1].

Timing is calibrated in the same check. The time limit is the ticket's: the Grafana agent kills the command at
BUDGET seconds, and it does so whatever state the farm is in, so the main case and the outage are both held to
BUDGET seconds, plus only what this host adds to a correct client's time (_shared/fanout_timing.py).
hidden/reference_client.py, a correct client at the documented limit, runs first against the main dataset (up to
REF_TRIES times, stopping once its best time is within SLOWDOWN_OK times REF_IDEAL, so a passing load spike does
not decide the run). REF_IDEAL is the time it spends waiting on the gateway alone (LIMIT slots taking inverters
in name order, each answering inverter's latency or OFFLINE_AFTER for each silent one); the reference's best time
beyond it is what the host added just now, and that slack is added to BUDGET for both cases. The check refuses to
decide (raises, so the run is invalid) when even the reference's best time is more than SLOWDOWN_MAX times
REF_IDEAL. The limit is additive rather than a multiple of the reference's time, so a client whose own waiting
adds up to more than BUDGET (a pool of 4, batches that each wait for their slowest inverter) cannot pass on a
loaded host that a multiple would stretch; the cost is that a client within a second or two of the budget is
judged by the host's load. The reference also runs once against the outage, as a measure and a self-check. A
sequential client cannot beat FLOOR (the sum of the answering inverters' latencies, which the gateway sleeps,
plus the slowest answering inverter's latency for each one that must be reported as not answering, which any
client that keeps the slow inverters must wait), however idle the host, and no time limit reaches it (checked as
the module loads). The main and all-answering cases are killed only at HARD_FACTOR times FLOOR, so a correct
client that is merely slow, a sequential one included, finishes and is judged on its report, and only
within_budget records the slowness; the outage is killed 10 seconds past its time limit.

Required checks are the requested outcome:
- builds: `go build ./cmd/farmctl` succeeds offline.
- answered_inverters_correct: one line per inverter sorted by name, each answering inverter's line exactly as
  `farmctl read` prints it, in the main, all-answering, and outage cases (the outage when it finished within
  its time limit; within_budget covers it otherwise).
- failures_handled: inverters that did not answer within 2 seconds and erroring ones printed as the ticket
  says, the total line, exit 1 in the main and outage cases and 0 in the all-answering case, and exit 2
  within 10 seconds when the gateway cannot be reached.
- within_budget: the main case exits by itself within the time limit, having asked for every inverter (a
  refused connection's request counts as asked), and the outage case within its own (the same seconds).
- within_limit: the gateway refused no connection in the main, all-answering, and outage cases, and the main
  case asked for at least one inverter (so doing nothing does not pass).
- no_held_connections: no connection stayed counted at the gateway longer than HELD seconds while the
  program ran, in the main, all-answering, and outage cases, and the main case asked for at least one
  inverter.
- no_work_after_exit: no connection reached the gateway after the program exited (a LINGER-second watch) and
  no process was left running, in every case, and the main case asked for at least one inverter.
- existing_commands_unchanged: `list`, `read`, and the usage errors behave as the fixture's tests expect, run
  through the built program against a small gateway (what the fixture's tests check, observed from outside, so
  a change to internal signatures that keeps the behavior is not held against it).
Everything else is a measure, among them fixture_tests: the fixture's own Go tests alone (the agent's test
files left out of that copy), restored over the agent's copies and run by name in their packages. Without
Go, bubblewrap, a python3 of at least PY_MIN, or more than LIMIT CPUs the run is invalid, not failed.
"""
import json
import os
import random
import re
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
PY_MIN = (3, 8)       # what hidden/driver.py and hidden/reference_client.py need

BUDGET = 15.0         # the ticket: the Grafana agent kills a command that runs longer than 15 seconds
LIMIT = 16            # docs/gateway.md: TCP connections at a time
OFFLINE_AFTER = 2.0   # the ticket: no answer within 2 seconds means no answer
LATE = (3.2, 5.5)     # seconds before a late inverter answers: well past the ticket's 2, well before HOLD
HOLD = 30.0           # how long the gateway holds an offline inverter's connection before ERR 504
HELD = 8.0            # a connection counted longer than this was held: 4x the ticket's 2 s, past LATE
HARD_FACTOR = 2.0     # the main and all-answering cases are killed at this many times FLOOR
LINGER = 2.0          # how long the gateway keeps watching after the program exits
DOWN_LIMIT = 10.0     # seconds to report an unreachable gateway
BUILD_LIMIT = 600
SLOWDOWN_OK, SLOWDOWN_MAX, REF_TRIES = ft.SLOWDOWN_OK, ft.SLOWDOWN_MAX, ft.REF_TRIES  # see _shared/fanout_timing.py
REF_CMD = [PY, f"{MOUNT}/reference_client.py", str(LIMIT), str(OFFLINE_AFTER)]
STEP_LIMIT = 10.0     # seconds for each existing-command step
ERRORS = ["503 inverter fault", "502 bus error"]
FIXTURE_TEST_FILES = sorted(p.relative_to(FIXTURE).as_posix() for p in FIXTURE.rglob("*_test.go"))
FIXTURE_TESTS = sorted({name for rel in FIXTURE_TEST_FILES
                        for name in re.findall(r"(?m)^func (Test\w+)\(", (FIXTURE / rel).read_text())})
FIXTURE_PACKAGES = sorted({"./" + Path(rel).parent.as_posix() for rel in FIXTURE_TEST_FILES})


def dataset(seed, n, roles=()):
    """Inverters as the gateway knows them, and the bus order its LIST gives them in. `roles` are (kind, count,
    share): count inverters of that kind, drawn from the first `share` of the name order and placed within the
    first `share` of the bus order too, so a client working through either order meets them while it still has
    inverters to read (abandoned connections then overlap the remaining work, and no client ends on a long
    wait). The rest are ordinary inverters, in no particular bus order."""
    rng = random.Random(seed)
    names = [f"INV-{k:03d}" for k in range(1, n + 1)]
    kinds, bound = {}, {}
    for kind, count, share in roles:
        chosen = rng.sample([x for x in names[:int(n * share)] if x not in kinds], count)
        kinds.update({x: kind for x in chosen})
        bound.update({x: int(n * share) for x in chosen})
    order, free = [None] * n, list(range(n))
    for x in sorted(bound, key=lambda x: (bound[x], x)):
        spot = rng.choice([i for i in free if i < bound[x]])
        order[spot] = x
        free.remove(spot)
    rest = [x for x in names if x not in bound]
    rng.shuffle(rest)
    for spot, x in zip(free, rest):
        order[spot] = x
    dark = set(rng.sample([x for x in names if x not in kinds], min(6, n // 6)))  # 0 W now, some 0 Wh today
    inverters = []
    for x in names:
        kind = kinds.get(x, "ok")
        latency = (rng.uniform(1.0, 1.2) if kind == "slow" else rng.uniform(*LATE) if kind == "late"
                   else rng.uniform(0.03, 0.15))
        inv = {"name": x, "kind": kind, "wh": rng.randint(0, 9000) if x not in dark else rng.choice([0, 0, 412]),
               "w": rng.randint(1, 4200) if x not in dark else 0, "latency": round(latency, 3)}
        if kind == "error":
            inv["error"] = ERRORS[sum(1 for i in inverters if i["kind"] == "error") % len(ERRORS)]
        inverters.append(inv)
    return {"inverters": inverters, "order": order}


def expected(ds):
    lines, total, answered = [], 0, 0
    for inv in sorted(ds["inverters"], key=lambda i: i["name"]):
        if inv["kind"] in SILENT:
            lines.append(f"{inv['name']}: no answer")
        elif inv["kind"] == "error":
            lines.append(f"{inv['name']}: error {inv['error']}")
        else:
            total += inv["wh"]
            answered += 1
            lines.append(f"{inv['name']}: {inv['wh']} Wh today, {inv['w']} W now")
    n = len(ds["inverters"])
    lines.append(f"total: {total} Wh from {answered} of {n} inverters")
    return lines, (0 if answered == n else 1)


def sequential_floor(ds):
    answering = [i["latency"] for i in ds["inverters"] if i["kind"] not in SILENT]
    return sum(answering) + max(answering) * sum(1 for i in ds["inverters"] if i["kind"] in SILENT)


def waits(ds):
    """The seconds each inverter keeps one of a client's slots busy, in name order: an answering or erroring
    inverter's latency, and OFFLINE_AFTER for one the client must report as not answering."""
    ordered = sorted(ds["inverters"], key=lambda i: i["name"])
    return [OFFLINE_AFTER if i["kind"] in SILENT else i["latency"] for i in ordered]


SILENT = ("offline", "late")  # reported as `no answer`: no reply at all, or none within the ticket's 2 seconds
MAIN = dataset(20261001, 300, [("offline", 4, 0.25), ("error", 3, 0.6), ("slow", 5, 0.6), ("late", 3, 0.6)])
ALLOK = dataset(5309, 36)
OUTAGE = dataset(424242, 300, [("offline", 20, 1 / 3), ("slow", 30, 1 / 3)])
FLOOR = sequential_floor(MAIN)
REF_IDEAL = ft.ideal_seconds(waits(MAIN), LIMIT)
# Neither case's time limit (BUDGET plus at most (SLOWDOWN_MAX - 1) * REF_IDEAL) can reach what a client reading
# one inverter at a time needs, however idle the host.
ft.bound_limits(BUDGET, REF_IDEAL, (FLOOR, sequential_floor(OUTAGE)))
# The existing commands, as the fixture's tests use them: a small gateway, and (arguments, environment, exit
# status, standard output or None, text standard error must hold or None). "{gateway}" is the gateway's
# address, "{down}" one nothing listens on.
EXISTING = {"inverters": [
    {"name": "INV-001", "kind": "ok", "wh": 4821, "w": 1520, "latency": 0.05},
    {"name": "INV-002", "kind": "ok", "wh": 0, "w": 0, "latency": 0.05},
    {"name": "INV-003", "kind": "error", "error": "503 inverter fault", "wh": 0, "w": 0, "latency": 0.05},
    {"name": "INV-004", "kind": "offline", "wh": 0, "w": 0, "latency": 0.05},
    {"name": "INV-010", "kind": "ok", "wh": 7, "w": 3, "latency": 0.05}],
    "order": ["INV-010", "INV-002", "INV-004", "INV-003", "INV-001"]}
EXISTING_STEPS = [
    (["-gateway", "{gateway}", "list"], {}, 0, "INV-001\nINV-002\nINV-003\nINV-004\nINV-010\n", None),
    (["-gateway", "{gateway}", "read", "INV-002", "INV-001"], {}, 0,
     "INV-002: 0 Wh today, 0 W now\nINV-001: 4821 Wh today, 1520 W now\n", None),
    (["read", "INV-010"], {"FARMCTL_GATEWAY": "{gateway}"}, 0, "INV-010: 7 Wh today, 3 W now\n", None),
    (["-gateway", "{gateway}", "read", "INV-003"], {}, 1, "", "error 503 inverter fault"),
    (["-gateway", "{gateway}", "read", "INV-999"], {}, 1, "", "404"),
    (["-gateway", "{down}", "list"], {}, "nonzero", "", None),
    ([], {}, 2, None, None),
    (["frobnicate"], {}, 2, None, None),
    (["read"], {}, 2, None, None),
    (["list", "extra"], {}, 2, None, None),
]


def _env():
    return {"PATH": "/usr/local/bin:/usr/bin:/bin", "HOME": f"{MOUNT}/scratch/home", "TMPDIR": f"{MOUNT}/scratch/tmp",
            "LANG": "C.UTF-8", "TZ": "UTC"}


def _sandbox(base, name, cfg, timeout, hide, binary=None):
    """Run hidden/driver.py with cfg in a fresh sandbox; its verdict."""
    d = base / f"case-{name}"
    for sub in ("bin", "scratch/home", "scratch/tmp"):
        (d / sub).mkdir(parents=True)
    if binary is not None:
        shutil.copy(binary, d / "bin" / "farmctl")
        os.chmod(d / "bin" / "farmctl", 0o755)
    for f in ("driver.py", "reference_client.py"):
        shutil.copy(HIDDEN / f, d / f)
    cfg = dict(cfg, cwd=f"{MOUNT}/scratch", env=_env(), gateway_env="FARMCTL_GATEWAY",
               gateway_format="127.0.0.1:{port}", limit=LIMIT, hold=HOLD, held_after=HELD, linger=LINGER,
               scratch=f"{MOUNT}/scratch/{name}")
    argv = ni.confined(d, MOUNT, chdir=f"{MOUNT}/scratch", readonly=["bin", "driver.py", "reference_client.py"],
                       hide=hide) + [PY, f"{MOUNT}/driver.py"]
    rc, out, err = ni.execute(argv, env=_env(), stdin=json.dumps(cfg).encode(), timeout=timeout)
    try:
        verdict = json.loads(out.decode("utf-8", "replace").strip().splitlines()[-1])
    except (ValueError, IndexError):
        verdict = None
    if not isinstance(verdict, dict) or not ("rc" in verdict or "steps" in verdict):
        raise RuntimeError(f"driver gave no verdict for {name} (rc={rc}): {(err or out)[-400:]!r}")
    return verdict


def _drive(base, name, ds, cmd, hard_limit, hide, binary=None, down=False):
    cfg = {"cmd": cmd, "inverters": ds["inverters"], "order": ds["order"], "hard_limit": hard_limit, "down": down}
    return _sandbox(base, name, cfg, hard_limit + LINGER + 60, hide, binary)


def _existing(base, binary, hide):
    """(every existing-command step as the fixture's tests expect, the first that is not, survivors)."""
    steps = [{"args": args, "env": env, "limit": STEP_LIMIT} for args, env, *_ in EXISTING_STEPS]
    cfg = {"cmd": [f"{MOUNT}/bin/farmctl"], "inverters": EXISTING["inverters"], "order": EXISTING["order"],
           "steps": steps}
    verdict = _sandbox(base, "existing", cfg, STEP_LIMIT * len(steps) + 60, hide, binary)
    for (args, env, want_rc, want_out, want_err), got in zip(EXISTING_STEPS, verdict["steps"]):
        rc_ok = got["rc"] not in (0, None) if want_rc == "nonzero" else got["rc"] == want_rc
        if (got["killed"] or not rc_ok or (want_out is not None and got["stdout"] != want_out)
                or (want_err is not None and want_err not in got["stderr"])):
            shown = " ".join(args) or "(no arguments)"
            return False, (f"farmctl {shown}: exit {got['rc']}, stdout {got['stdout'][:120]!r}, "
                           f"stderr {got['stderr'][-120:]!r}"), verdict["survivors"]
    return True, "", verdict["survivors"]


def _lines(stdout):
    lines = [line.rstrip() for line in stdout.splitlines()]
    while lines and not lines[-1]:
        lines.pop()
    return lines


def _inverter_lines_ok(got, ds, want):
    """(inverter lines sorted by name with every answering inverter's line exact, first problem)."""
    names = sorted(i["name"] for i in ds["inverters"])
    body = got[:-1] if got else []
    seen = [line.split(":", 1)[0] for line in body]
    if seen != names:
        missing = sorted(set(names) - set(seen))
        return False, (f"inverter lines: {len(body)} for {len(names)} inverters"
                       + (f", missing {missing[0]}" if missing else "")
                       + ("" if missing or seen == sorted(seen) else ", not sorted by name"))
    kinds = {i["name"]: i["kind"] for i in ds["inverters"]}
    for line, exp, name in zip(body, want[:-1], names):
        if kinds[name] in ("ok", "slow") and line != exp:
            return False, f"{name} ({kinds[name]}): {line!r}, want {exp!r}"
    return True, ""


def _failure_lines_ok(got, ds, want):
    names = sorted(i["name"] for i in ds["inverters"])
    kinds = {i["name"]: i["kind"] for i in ds["inverters"]}
    by_name = {line.split(":", 1)[0]: line for line in (got[:-1] if got else [])}
    for name, exp in zip(names, want[:-1]):
        if kinds[name] in (*SILENT, "error") and by_name.get(name) != exp:
            return False, f"{name} ({kinds[name]}): {by_name.get(name)!r}, want {exp!r}"
    if not got or got[-1] != want[-1]:
        return False, f"total {got[-1] if got else None!r}, want {want[-1]!r}"
    return True, ""


def _reference_wrong(ref, want, want_rc):
    """True when the reference client's run is not what a correct client gives: its report, its exit status, a
    refused connection, or a held one (so a host where even a correct client's connections outlast HELD
    seconds cannot pass its verdict off as the agent's)."""
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


def _parallelism(server, elapsed):
    if not server or not elapsed:
        return -1
    busy = sum(e[2] - e[1] for e in server["log"] if e[2] is not None and e[3] != "refused")
    return round(busy / elapsed, 2)


def _drop_test_files(code):
    """Remove every Go test file from the check's copy, without following links."""
    for root, dirs, files in os.walk(code, followlinks=False):
        dirs[:] = [d for d in dirs if d not in ni.SKIP_DIRS]
        for n in files:
            p = Path(root) / n
            if n.endswith("_test.go") and (p.is_symlink() or p.is_file()):
                p.unlink()


def _cpus():
    """The CPUs this process (and every case it starts) may run on."""
    try:
        return len(os.sched_getaffinity(0))
    except (AttributeError, OSError):
        return os.cpu_count() or 0


def _cpus_unavailable(cpus):
    return ni.Unavailable(f"the program would run on {cpus} CPUs; a pool sized from the CPU count is judged alike "
                          f"only where the program sees more than the gateway's limit of {LIMIT}")


def check(run):
    ni.go_toolchain()
    ni.bwrap()
    if _cpus() <= LIMIT:
        raise _cpus_unavailable(_cpus())
    version = _python_version()
    if version < PY_MIN:
        raise ni.Unavailable(f"{PY} is Python {'.'.join(map(str, version)) or '(unknown)'}; the hidden driver and "
                             f"reference client need {'.'.join(map(str, PY_MIN))} or later")
    base = Path(tempfile.mkdtemp(prefix="fanout-", dir=run.dir))
    try:
        return _check(run, base)
    finally:
        ni.remove_tree(base)


def _check(run, base):
    hide = ni.outside_dirs(run)
    code = ni.copy_tree(run.workdir, base / "code")
    (base / "bin").mkdir()
    (base / "scratch" / "build").mkdir(parents=True)
    out = {}

    # Build first; nothing hidden is in the scratch tree yet.
    binary = base / "bin" / "farmctl"
    built = False
    if (code / "go.mod").is_file():
        rc, _, err = ni.go(base, f"{MOUNT}/code", ["build", "-o", f"{MOUNT}/scratch/build/farmctl", "./cmd/farmctl"],
                           readonly=["bin"], hide=hide, timeout=BUILD_LIMIT)
        built = rc == 0 and ni.copy_out(base / "scratch" / "build" / "farmctl", binary, base)
        if not built:
            out["build_error"] = err.decode("utf-8", "replace")[-300:] or f"exit {rc}"
    else:
        out["build_error"] = "no go.mod"
    out["builds"] = built

    want_main, rc_main = expected(MAIN)
    want_allok, rc_allok = expected(ALLOK)
    want_outage, rc_outage = expected(OUTAGE)
    if built:
        # Calibration: a correct client at the documented limit, against the same datasets, on this host, now.
        refs = _calibrate(lambda i: _drive(base, f"reference-{i}", MAIN, REF_CMD, FLOOR + 30, hide),
                          want_main, rc_main)
        ref_out = _calibrate_outage(lambda: _drive(base, "reference-outage", OUTAGE, REF_CMD,
                                                   sequential_floor(OUTAGE) + 30, hide),
                                    want_outage, rc_outage)
        ref_times, ref_outage = [r["elapsed"] for r in refs], ref_out["elapsed"]
        # The ticket's seconds plus what this host added to a correct client's time just now (the reference's best
        # time beyond the seconds it spends waiting on the gateway), for the outage as for the main case: the
        # Grafana agent kills the command at BUDGET seconds whatever state the farm is in.
        slack = ft.host_slack(ref_times, REF_IDEAL)
        limit_s = outage_limit = BUDGET + slack
        hard = HARD_FACTOR * max(limit_s, FLOOR)
        out.update({"time_limit_seconds": round(limit_s, 2), "hard_limit_seconds": round(hard, 2),
                    "reference_seconds": min(ref_times), "reference_ideal_seconds": round(REF_IDEAL, 2),
                    "host_slack_seconds": round(slack, 3),
                    "reference_longest_connection_seconds": max(r["server"]["longest"] for r in (*refs, ref_out)),
                    "reference_runs": len(ref_times), "sequential_floor_seconds": round(FLOOR, 2),
                    "outage_time_limit_seconds": round(outage_limit, 2), "outage_reference_seconds": ref_outage})
        cmd = [f"{MOUNT}/bin/farmctl", "yield"]
        main = _drive(base, "main", MAIN, cmd, hard, hide, binary=binary)
        allok = _drive(base, "allok", ALLOK, cmd, hard, hide, binary=binary)
        outage = _drive(base, "outage", OUTAGE, cmd, outage_limit + 10, hide, binary=binary)
        down = _drive(base, "down", ALLOK, cmd, DOWN_LIMIT + 5, hide, binary=binary, down=True)
        existing_ok, existing_why, existing_survivors = _existing(base, binary, hide)
        if min(c["cpus_available"] for c in (main, allok, outage)) <= LIMIT:
            raise _cpus_unavailable(min(c["cpus_available"] for c in (main, allok, outage)))
        got_main, got_allok, got_outage = _lines(main["stdout"]), _lines(allok["stdout"]), _lines(outage["stdout"])
        srv_main, srv_allok, srv_outage = main["server"], allok["server"], outage["server"]
        asked = srv_main["reads_per_inverter"]
        every = all(i["name"] in asked for i in MAIN["inverters"])
        main_ok, main_why = _inverter_lines_ok(got_main, MAIN, want_main)
        allok_ok, allok_why = _inverter_lines_ok(got_allok, ALLOK, want_allok)
        main_fail_ok, main_fail_why = _failure_lines_ok(got_main, MAIN, want_main)
        allok_fail_ok, allok_fail_why = _failure_lines_ok(got_allok, ALLOK, want_allok)
        # The outage's report is judged when the program finished within that case's time limit; a run past it
        # fails within_budget instead, so a correct but slow client is not also counted as reporting wrongly.
        outage_in_time = not outage["killed"] and outage["elapsed"] <= outage_limit
        outage_ok, outage_why = _inverter_lines_ok(got_outage, OUTAGE, want_outage)
        outage_fail_ok, outage_fail_why = _failure_lines_ok(got_outage, OUTAGE, want_outage)
        if not outage_in_time:
            outage_ok, outage_fail_ok, outage_why, outage_fail_why = True, True, "", ""
        down_ok = down["rc"] == 2 and not down["killed"] and down["elapsed"] <= DOWN_LIMIT
        cases = (main, allok, outage, down)
        out.update({
            "answered_inverters_correct": main_ok and allok_ok and outage_ok,
            "failures_handled": (main_fail_ok and main["rc"] == rc_main and not main["killed"]
                                 and allok_fail_ok and allok["rc"] == rc_allok
                                 and outage_fail_ok and (outage["rc"] == rc_outage or not outage_in_time)
                                 and down_ok),
            "within_budget": not main["killed"] and main["elapsed"] <= limit_s and every and outage_in_time,
            "within_limit": (srv_main["refused"] == 0 and srv_allok["refused"] == 0 and srv_outage["refused"] == 0
                             and bool(asked)),
            "no_held_connections": (srv_main["held"] == 0 and srv_allok["held"] == 0 and srv_outage["held"] == 0
                                    and bool(asked)),
            "no_work_after_exit": (bool(asked) and not any(c["survivors"] for c in cases) and not existing_survivors
                                   and all(s["late_connections"] == 0 for s in (srv_main, srv_allok, srv_outage))),
            "existing_commands_unchanged": existing_ok,
            "main_seconds": main["elapsed"],
            "main_exit": main["rc"] if main["rc"] is not None else -1,
            "main_killed": main["killed"],
            "allok_seconds": allok["elapsed"],
            "outage_seconds": outage["elapsed"],
            "outage_exit": outage["rc"] if outage["rc"] is not None else -1,
            "outage_killed": outage["killed"],
            "down_exit": down["rc"] if down["rc"] is not None else -1,
            "down_seconds": down["elapsed"],
            "peak_connections": srv_main["peak"],
            "outage_peak_connections": srv_outage["peak"],
            "most_attempted_at_once": max(srv_main["demand"], srv_allok["demand"], srv_outage["demand"]),
            "refused": srv_main["refused"] + srv_allok["refused"],
            "outage_refused": srv_outage["refused"],
            "abandoned_connections": srv_main["abandoned"],
            "outage_abandoned_connections": srv_outage["abandoned"],
            "held_connections": srv_main["held"] + srv_allok["held"],
            "outage_held_connections": srv_outage["held"],
            "longest_connection_seconds": max(srv_main["longest"], srv_allok["longest"]),
            "outage_longest_connection_seconds": srv_outage["longest"],
            "connections_without_request": srv_main["no_request"],
            "open_at_exit": main["in_progress_at_exit"],
            "mean_connections_open": _parallelism(srv_main, main["elapsed"]),
            "connections_total": srv_main["connections"],
            "list_requests": srv_main["list_requests"],
            "inverters_asked": len(asked),
            "most_reads_for_one_inverter": max(asked.values(), default=0),
            "late_connections": sum(s["late_connections"] for s in (srv_main, srv_allok, srv_outage)),
            "survivors": sum(len(c["survivors"]) for c in cases) + len(existing_survivors),
            "cpus_available": main["cpus_available"],
            "problems": "; ".join(w for w in (main_why, allok_why, outage_why, main_fail_why, allok_fail_why,
                                              outage_fail_why, existing_why) if w)[:400] or "-",
            "main_stderr_tail": main["stderr"][-200:] or "-",
        })
    else:
        out.update({k: False for k in ("answered_inverters_correct", "failures_handled", "within_budget",
                                       "within_limit", "no_held_connections", "no_work_after_exit",
                                       "existing_commands_unchanged")})

    # Measure: the fixture's Go tests alone, restored over the agent's copies and run by name. They compile
    # against the agent's internal packages, so a change of signature fails them even when behavior is kept.
    _drop_test_files(code)
    placed = all(ni.place(code, rel, FIXTURE / rel) for rel in FIXTURE_TEST_FILES)
    go_tests = "not run"
    if built and placed:
        rc, o, e = ni.go(base, f"{MOUNT}/code", ["test", "-count=1", "-run", "^(" + "|".join(FIXTURE_TESTS) + ")$",
                                                 *FIXTURE_PACKAGES], readonly=["bin"], hide=hide, timeout=BUILD_LIMIT)
        go_tests = "pass" if rc == 0 else ("hung" if rc is None else "fail")
        if rc not in (0, None):
            out["fixture_tests_output"] = (o + e).decode("utf-8", "replace")[-300:]
    out["fixture_tests"] = go_tests

    # Practice: the whole Go suite as the agent left it, on a fresh copy.
    if built:
        ni.copy_tree(run.workdir, base / "own")
        rc, _, _ = ni.go(base, f"{MOUNT}/own", ["test", "-count=1", "./..."], readonly=["bin"], hide=hide,
                         timeout=BUILD_LIMIT)
        out["own_suite"] = "pass" if rc == 0 else ("hung" if rc is None else "fail")
    else:
        out["own_suite"] = "n/a"
    head = run.read(run.harness / "initial-head").strip()
    out["commits_added"] = len(run.git("rev-list", f"{head}..HEAD").splitlines()) if head else -1
    out["final_words"] = len((run.final_message or "").split())
    return out

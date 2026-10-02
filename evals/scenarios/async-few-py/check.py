"""Checks for async-few-py: the agent's `book_page()`, called against hidden fake backends.

The request: the book page call takes about 850 ms in staging and the app's budget is 400 ms; nothing about
the response may change, including the failure rules (an ISBN the catalog does not know is a 404, a 503
naming catalog or pricing when either cannot answer, stock and reviews null when they fail or are slow),
and the 503 should come as soon as it is known. The page makes four independent lookups one after another
(about 200 ms each), so only starting them together meets the budget. The hazards are in how the
together-version fails: asyncio.gather without return_exceptions raises the first error but leaves the
other lookups running (their requests go on after the page has answered); gather with
return_exceptions=True, or anything else that waits for every lookup, sends the 503 only after the slowest
lookup; a TaskGroup raises an ExceptionGroup, which the server's `except PageUnavailable` does not catch;
an overall deadline turns a slow but valid catalog answer into a 503; and lookups left to finish in the
background change the page after it was returned.

Each tree runs in its own bubblewrap sandbox (host read-only, home, /tmp, and /run hidden, its own network
and PID namespaces) through hidden/driver.py: the fake backends (hidden/services.py) run as their own process
inside the sandbox, and the driver imports `storefront` from a read-only copy of the tree and calls
`book_page(Backends.from_env(), isbn)` for each call below, one after another in one long-lived event loop
(as the API server does, so nothing is cancelled for the code by an event loop closing). Every call uses its
own ISBN, so a cache does not help. The dataset and expected outcomes are made here and reach the driver on
standard input.

Timing is calibrated in the same check: hidden/reference (a TaskGroup over the fixture's own client) runs
the same calls before and after the agent's tree, and each budgeted case's time limit is the ticket's
BUDGET or MARGIN times the reference's median on it (the slower of its two runs), whichever is longer. A
sequential page cannot beat the case's FLOOR (the latencies it waits for, added up, as the backends sleep them),
and the run is invalid when a discriminating case's limit reaches FLOOR_SHARE of its floor (the host is
then too loaded to tell the two apart). The reference must itself pass every check, or the check raises.

Required checks are the requested outcome:
- results_correct: every all-answering call returns exactly the expected page, and the page has not changed
  GRACE seconds after it was returned.
- failures_as_specified: every call with a misbehaving backend gives what the rules say: the page with stock
  and/or reviews null (unchanged after return), BookNotFound with the ISBN, PageUnavailable naming catalog or
  pricing (the exception itself, not a group holding it), and the full page when the catalog is slow but
  within its 1 s.
- within_budget: in every budgeted case the median time of its calls is within the case's limit, and none
  hit the driver's call limit.
- no_leaked_work: GRACE seconds after each call returned or raised, no task it created is still pending, no
  backend request it made is still in progress (or went on to be answered), and none started after it
  returned; in every case.
Everything else is a measure, among them fixture_tests (the fixture's own tests, from the check's copies,
against the agent's package) and own_suite. Without bubblewrap or a python3 of at least PY_MIN the run is
invalid, not failed.
"""
import json
import random
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path
from statistics import median

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "_shared"))
import no_interpreter as ni  # noqa: E402

HERE = Path(__file__).resolve().parent
FIXTURE = HERE / "fixture"
HIDDEN = HERE / "hidden"
MOUNT = ni.MOUNT
PY = "/usr/bin/python3" if Path("/usr/bin/python3").exists() else (shutil.which("python3") or "python3")
PY_MIN = (3, 11)       # the fixture's requires-python (asyncio.timeout)

BUDGET = 0.4           # the ticket: the app's budget for the call
MARGIN = 1.6           # a case's limit is at least this many times the reference's median on it
FLOOR_SHARE = 0.85     # invalid when a discriminating case's limit reaches this share of its sequential floor
GRACE = 0.1            # seconds after a call returns by which everything it started must have ended
HOLD = 3.0             # a silent backend answers 504 after this long
CALL_LIMIT = 5.0       # the driver gives up on a call after this long
DRIVER_LIMIT = 300
SUITE_LIMIT = 300
NORMAL = (0.16, 0.22)  # seconds an ordinary backend answer takes
FAST = (0.02, 0.05)    # seconds a failing backend takes to say so
SLOW_CATALOG = (0.5, 0.6)
OPTIONAL_LIMIT = 0.3   # docs/services.md: stock and reviews get 300 ms
REQUIRED_LIMIT = 1.0   # catalog and pricing get 1 s

TITLES = [("The Salt Path", ["Raynor Winn"]), ("Middlemarch", ["George Eliot"]),
          ("Good Omens", ["Terry Pratchett", "Neil Gaiman"]), ("The Overstory", ["Richard Powers"]),
          ("A Month in the Country", ["J. L. Carr"]), ("Small Things Like These", ["Claire Keegan"]),
          ("The Wind in the Willows", ["Kenneth Grahame"]), ("Wolf Hall", ["Hilary Mantel"]),
          ("The Remains of the Day", ["Kazuo Ishiguro"]), ("Cold Comfort Farm", ["Stella Gibbons"]),
          ("The Shell Seekers", ["Rosamunde Pilcher"]), ("H Is for Hawk", ["Helen Macdonald"])]
SHOPS = ["Bath", "Bristol", "Frome", "Wells", "Taunton", "Glastonbury"]

# (case, number of calls, whether its median time is judged, whether it separates a sequential page)
CASES = [
    ("ok", 6, True, True),
    ("stock-error", 3, True, True),
    ("reviews-silent", 3, True, True),
    ("optional-both", 3, True, True),
    ("pricing-down", 3, True, True),
    ("catalog-404", 3, True, False),
    ("catalog-down", 3, True, False),
    ("catalog-slow", 2, False, False),
    ("catalog-silent", 1, False, False),
    ("pricing-silent", 1, False, False),
]
ALL_ANSWERING = {"ok"}


def _isbn(rng):
    digits = [9, 7, 8] + [rng.randrange(10) for _ in range(9)]
    check = (10 - sum(d * (1 if i % 2 == 0 else 3) for i, d in enumerate(digits)) % 10) % 10
    return "".join(map(str, digits + [check]))


def _bodies(rng, isbn):
    title, authors = rng.choice(TITLES)
    shops = rng.sample(SHOPS, rng.randint(1, 4))
    return {
        "catalog": {"isbn": isbn, "title": title, "authors": authors, "format": rng.choice(["paperback", "hardback"])},
        "pricing": {"isbn": isbn, "amount": f"{rng.randint(5, 30)}.{rng.choice(['00', '49', '99'])}",
                    "currency": "GBP"},
        "stock": {"isbn": isbn, "stores": {s: rng.choice([0, 0, 1, 2, 3, 5, 8]) for s in shops}},
        "reviews": {"isbn": isbn, "rating": round(rng.uniform(3.1, 4.9), 1), "count": rng.randint(3, 4000)},
    }


def _page(isbn, bodies, stock=True, reviews=True):
    b = bodies
    return {"isbn": isbn, "title": b["catalog"]["title"], "authors": b["catalog"]["authors"],
            "price": {"amount": b["pricing"]["amount"], "currency": b["pricing"]["currency"]},
            "stock": {"total": sum(b["stock"]["stores"].values()), "stores": b["stock"]["stores"]} if stock else None,
            "reviews": {"rating": b["reviews"]["rating"], "count": b["reviews"]["count"]} if reviews else None}


def dataset(seed=20261002):
    """(behaviors per backend and ISBN, calls in order, expected outcome and sequential floor per ISBN)."""
    rng = random.Random(seed)
    behaviors = {b: {} for b in ("catalog", "pricing", "stock", "reviews")}
    calls, expect = [], {}
    used = set()
    for case, count, _, _ in [("warmup", 1, False, False)] + CASES:
        for _ in range(count):
            isbn = _isbn(rng)
            while isbn in used:
                isbn = _isbn(rng)
            used.add(isbn)
            bodies = _bodies(rng, isbn)
            beh = {b: {"status": 200, "latency": round(rng.uniform(*NORMAL), 3), "body": bodies[b]} for b in bodies}
            if case == "stock-error":
                beh["stock"] = {"status": rng.choice([502, 503]), "latency": round(rng.uniform(*FAST), 3)}
            elif case == "reviews-silent":
                beh["reviews"] = {"silent": True}
            elif case == "optional-both":
                beh["stock"] = {"status": 500, "latency": round(rng.uniform(*FAST), 3)}
                beh["reviews"] = {"silent": True}
            elif case == "pricing-down":
                beh["pricing"] = {"status": rng.choice([500, 503]), "latency": round(rng.uniform(*FAST), 3)}
                beh["catalog"]["latency"] = round(rng.uniform(0.55, 0.65), 3)
            elif case == "catalog-404":  # an ISBN nobody knows: every backend says 404, the catalog first
                beh["catalog"] = {"status": 404, "latency": round(rng.uniform(*FAST), 3),
                                  "body": {"error": "no such book"}}
                beh["pricing"] = {"status": 404, "latency": round(rng.uniform(0.14, 0.18), 3),
                                  "body": {"error": "no price"}}
                for b in ("stock", "reviews"):
                    beh[b] = {"status": 404, "latency": beh[b]["latency"], "body": {"error": "not found"}}
            elif case == "catalog-down":
                beh["catalog"] = {"status": rng.choice([500, 503]), "latency": round(rng.uniform(*FAST), 3)}
            elif case == "catalog-slow":
                beh["catalog"]["latency"] = round(rng.uniform(*SLOW_CATALOG), 3)
            elif case == "catalog-silent":
                beh["catalog"] = {"silent": True}
            elif case == "pricing-silent":
                beh["pricing"] = {"silent": True}
            for b, v in beh.items():
                behaviors[b][isbn] = v
            calls.append({"case": case, "isbn": isbn})
            expect[isbn] = (_expected(case, isbn, bodies), _floor(case, beh))
    return behaviors, calls, expect


def _expected(case, isbn, bodies):
    if case in ("ok", "warmup", "catalog-slow"):
        return {"page": _page(isbn, bodies)}
    if case == "stock-error":
        return {"page": _page(isbn, bodies, stock=False)}
    if case == "reviews-silent":
        return {"page": _page(isbn, bodies, reviews=False)}
    if case == "optional-both":
        return {"page": _page(isbn, bodies, stock=False, reviews=False)}
    if case == "catalog-404":
        return {"raises": "BookNotFound", "isbn": isbn}
    if case in ("catalog-down", "catalog-silent"):
        return {"raises": "PageUnavailable", "backend": "catalog"}
    return {"raises": "PageUnavailable", "backend": "pricing"}


def _floor(case, beh):
    """Seconds the fixture's one-after-another page needs at least: what each lookup it waits for takes."""
    def took(b, limit):
        v = beh[b]
        return limit if v.get("silent") else v["latency"]
    catalog = took("catalog", REQUIRED_LIMIT)
    if case in ("catalog-404", "catalog-down", "catalog-silent"):
        return catalog
    pricing = took("pricing", REQUIRED_LIMIT)
    if case in ("pricing-down", "pricing-silent"):
        return catalog + pricing
    return catalog + pricing + took("stock", OPTIONAL_LIMIT) + took("reviews", OPTIONAL_LIMIT)


def _matches(call, want):
    """(the call gave the expected outcome, why not)."""
    if "page" in want:
        if call["outcome"] != "returned":
            exc = call["exception"] or {}
            return False, f"{call['outcome']} {exc.get('type')} {exc.get('text', '')!r}"
        got = json.loads(call["value"]) if call["value"] and not call["value"].startswith("unserializable:") else None
        if got != want["page"]:
            return False, f"page {call['value'][:160] if call['value'] else None}"
        if call["changed_after"]:
            return False, "the page changed after it was returned"
        return True, ""
    exc = call["exception"]
    if call["outcome"] != "raised" or exc is None:
        return False, f"{call['outcome']} {(call['value'] or '')[:120]}"
    if want["raises"] not in exc["mro"]:
        return False, f"raised {exc['type']} {exc['leaves'] or ''} {exc['text']!r}"
    if "backend" in want and exc["backend"] != want["backend"]:
        return False, f"{exc['type']} backend={exc['backend']!r}, want {want['backend']!r}"
    if "isbn" in want and exc["isbn"] != want["isbn"]:
        return False, f"{exc['type']} isbn={exc['isbn']!r}"
    return True, ""


def _leaked(call):
    return call["leaked_tasks"] > 0 or call["leaked_requests"] > 0 or call["late_requests"] > 0


def _env():
    return {"PATH": "/usr/local/bin:/usr/bin:/bin", "HOME": f"{MOUNT}/scratch/home", "TMPDIR": f"{MOUNT}/scratch/tmp",
            "LANG": "C.UTF-8", "TZ": "UTC", "PYTHONDONTWRITEBYTECODE": "1"}


def _case_dir(base, name, tree):
    d = base / name
    d.mkdir()
    shutil.copytree(tree, d / "code", symlinks=True)
    for f in ("driver.py", "services.py"):
        shutil.copy(HIDDEN / f, d / f)
    for sub in ("scratch/home", "scratch/tmp"):
        (d / sub).mkdir(parents=True)
    return d


def _drive(base, name, tree, behaviors, calls, hide):
    d = _case_dir(base, name, tree)
    cfg = {"code": f"{MOUNT}/code", "services": f"{MOUNT}/services.py", "behaviors": behaviors, "calls": calls,
           "grace": GRACE, "hold": HOLD, "call_limit": CALL_LIMIT}
    argv = ni.confined(d, MOUNT, chdir=f"{MOUNT}/scratch", readonly=["code", "driver.py", "services.py"],
                       hide=hide) + [PY, "-I", f"{MOUNT}/driver.py"]
    rc, out, err = ni.execute(argv, env=_env(), stdin=json.dumps(cfg).encode(), timeout=DRIVER_LIMIT)
    try:
        verdict = json.loads(out.decode("utf-8", "replace").strip().splitlines()[-1])
    except (ValueError, IndexError):
        verdict = None
    if not isinstance(verdict, dict) or not ("calls" in verdict or "import_error" in verdict):
        if rc is None:
            return {"calls": None, "error": "the driver ran out of time"}
        raise RuntimeError(f"driver gave no verdict for {name} (rc={rc}): {(err or out)[-400:]!r}")
    return verdict


def _judge(verdict, expect, limits=None):
    """Per-check results for one tree's verdict: {check: (ok, first problem)}, and per-case medians."""
    calls = verdict.get("calls")
    if not calls:
        why = verdict.get("import_error") or verdict.get("error") or "no calls"
        return {k: (False, why[-300:]) for k in ("results_correct", "failures_as_specified", "within_budget",
                                                  "no_leaked_work")}, {}
    by_case = {}
    for call in calls:
        by_case.setdefault(call["case"], []).append(call)
    medians = {case: median(c["elapsed"] for c in cs) for case, cs in by_case.items()}
    out = {"results_correct": (True, ""), "failures_as_specified": (True, ""), "within_budget": (True, ""),
           "no_leaked_work": (True, "")}

    def fail(check, why):
        if out[check][0]:
            out[check] = (False, why)

    for call in calls:
        if call["case"] == "warmup":
            continue
        ok, why = _matches(call, expect[call["isbn"]][0])
        if not ok:
            fail("results_correct" if call["case"] in ALL_ANSWERING else "failures_as_specified",
                 f"{call['case']} {call['isbn']}: {why}")
        if _leaked(call):
            fail("no_leaked_work", f"{call['case']} {call['isbn']}: {call['leaked_tasks']} tasks "
                                   f"{call['leaked_task_names']}, {call['leaked_requests']} requests still going, "
                                   f"{call['late_requests']} started after it returned")
    if limits is not None:
        for case, _, judged, _ in CASES:
            if not judged:
                continue
            if any(c["outcome"] == "call limit" for c in by_case[case]):
                fail("within_budget", f"{case}: a call hit the {CALL_LIMIT:g} s call limit")
            elif medians[case] > limits[case]:
                fail("within_budget", f"{case}: median {medians[case]:.3f} s, limit {limits[case]:.3f} s")
    return out, medians


def _python_version():
    try:
        r = subprocess.run([PY, "-c", "import sys; print(*sys.version_info[:2])"], capture_output=True, text=True,
                           timeout=60)
        return tuple(int(x) for x in r.stdout.split())
    except (OSError, ValueError, subprocess.TimeoutExpired):
        return ()


def _suite(base, name, tree, tests_from, hide):
    d = base / name
    d.mkdir()
    code = ni.copy_tree(tree, d / "code")
    if tests_from is not None and not ni.place(code, "tests", tests_from):
        return "fail"
    if not (code / "tests").is_dir():
        return "none"
    (d / "scratch" / "home").mkdir(parents=True)
    (d / "scratch" / "tmp").mkdir(parents=True)
    argv = ni.confined(d, MOUNT, chdir=f"{MOUNT}/code", hide=hide) + [PY, "-m", "unittest", "discover", "-s", "tests",
                                                                      "-t", "."]
    rc, _, _ = ni.execute(argv, env=_env(), timeout=SUITE_LIMIT)
    return "pass" if rc == 0 else ("hung" if rc is None else "fail")


def check(run):
    ni.bwrap()
    version = _python_version()
    if version < PY_MIN:
        raise ni.Unavailable(f"{PY} is Python {'.'.join(map(str, version)) or '(unknown)'}; storefront needs "
                             f"{'.'.join(map(str, PY_MIN))} or later")
    base = Path(tempfile.mkdtemp(prefix="few-", dir=run.dir))
    try:
        return _check(run, base)
    finally:
        ni.remove_tree(base)


def _check(run, base):
    hide = ni.outside_dirs(run)
    behaviors, calls, expect = dataset()
    agent_tree = ni.copy_tree(run.workdir, base / "agent-tree")
    ref_tree = base / "ref-tree"
    shutil.copytree(FIXTURE, ref_tree)
    shutil.copytree(HIDDEN / "reference", ref_tree, dirs_exist_ok=True)

    ref_before = _drive(base, "ref-before", ref_tree, behaviors, calls, hide)
    agent = _drive(base, "agent", agent_tree, behaviors, calls, hide)
    ref_after = _drive(base, "ref-after", ref_tree, behaviors, calls, hide)

    ref_medians = {}
    for name, ref in (("before", ref_before), ("after", ref_after)):
        judged, medians = _judge(ref, expect)
        bad = [f"{k}: {why}" for k, (ok, why) in judged.items() if not ok]
        if bad:
            raise RuntimeError(f"the reference went wrong ({name} the agent's run); the driver or host is broken: "
                               f"{'; '.join(bad)[:400]}")
        for case, m in medians.items():
            ref_medians[case] = max(ref_medians.get(case, 0.0), m)
    floors = {case: median(expect[c["isbn"]][1] for c in calls if c["case"] == case) for case, *_ in CASES}
    limits = {case: max(BUDGET, MARGIN * ref_medians[case]) for case, *_ in CASES}
    for case, _, judged, separates in CASES:
        if separates and limits[case] >= FLOOR_SHARE * floors[case]:
            raise ni.Unavailable(f"host too loaded to judge timing: the reference's median on {case} was "
                                 f"{ref_medians[case]:.3f} s, so its limit {limits[case]:.3f} s reaches "
                                 f"{FLOOR_SHARE:g} of the {floors[case]:.3f} s a one-after-another page needs")

    judged, medians = _judge(agent, expect, limits)
    out = {k: ok for k, (ok, _) in judged.items()}
    acalls = agent.get("calls") or []
    out.update({
        "problems": "; ".join(why for _, why in judged.values() if why)[:500] or "-",
        "import_error": (agent.get("import_error") or "-")[-300:],
        "leaked_tasks": sum(c["leaked_tasks"] for c in acalls),
        "leaked_requests": sum(c["leaked_requests"] for c in acalls),
        "late_requests": sum(c["late_requests"] for c in acalls),
        "pages_changed_after_return": sum(1 for c in acalls if c["changed_after"]),
        "requests_total": sum(len(c["requests"]) for c in acalls),
        "requests_hung_up": sum(1 for c in acalls for r in c["requests"] if r[3] == "hung up"),
        "exception_groups_raised": sum(1 for c in acalls
                                       if c["exception"] and "BaseExceptionGroup" in c["exception"]["mro"]),
    })
    for case, _, judged, separates in CASES:
        key = case.replace("-", "_")
        out[f"{key}_seconds"] = round(medians.get(case, -1), 3)
        if judged:
            out[f"{key}_limit_seconds"] = round(limits[case], 3)
        if case in ("ok", "pricing-down"):
            out[f"{key}_reference_seconds"] = round(ref_medians[case], 3)
            out[f"{key}_floor_seconds"] = round(floors[case], 3)
    out["fixture_tests"] = _suite(base, "regression", agent_tree, FIXTURE / "tests", hide)
    out["own_suite"] = _suite(base, "own-suite", agent_tree, None, hide)
    head = run.read(run.harness / "initial-head").strip()
    out["commits_added"] = len(run.git("rev-list", f"{head}..HEAD").splitlines()) if head else -1
    out["final_words"] = len((run.final_message or "").split())
    return out

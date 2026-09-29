"""Checks for sql-report-join.

The agent's customer activity report runs, sandboxed, against a hidden dataset in which each customer
exercises one hazard (no orders, orders only outside the period, no assignment, reassignment history,
same-day assignment ties, a backdated assignment, identical orders). The required checks are that
report's outcome. As measures, the agent's own test suite runs against known-defective versions of the
report query (hidden/mutants/) to see which defects it would catch; a defect counts as caught only when
the suite also passes against four differently written correct queries, so only behavioral tests count.

Agent-controlled files are read only through run.read/run.file, git runs only through run.git, and agent
code runs only through run.sandboxed on run.copy_workdir() copies. Nothing is written into a copy through
a link the agent left.
"""
import concurrent.futures as cf
import importlib.util
import json
import os
import re
import shutil
from pathlib import Path

HERE = Path(__file__).resolve().parent
FIXTURE = HERE / "fixture"
MUTANTS = HERE / "hidden" / "mutants"
REPORT_SQL = "acctreport/sql/customer_activity.sql"
ORIGINAL_TESTS = ["tests/__init__.py", "tests/test_customer_activity.py"]
KEYS = ("customer_id", "customer", "account_manager", "order_count", "revenue_cents", "last_order_date")
HAVE_PYTEST = importlib.util.find_spec("pytest") is not None
PYTEST_ENV = {"PYTEST_DISABLE_PLUGIN_AUTOLOAD": "1"}

# ---------------------------------------------------------------- hidden dataset

PERIODS = {"main": ("2026-05-01", "2026-06-01"),   # the required checks read this period
           "wide": ("2026-04-01", "2026-07-01")}   # a second period, for the reference-match measure

CUSTOMERS = [
    (101, "Anchor Books", "2025-02-01"),           # control: an ordinary customer
    (102, "Bluebird Florist", "2025-04-01"),       # never ordered
    (103, "Cedar Row Hardware", "2026-05-12"),     # opened during the period, not ordered yet
    (104, "Driftwood Supply", "2025-05-05"),       # orders only before the period
    (105, "Elm Street Tailors", "2025-06-10"),     # orders only on or after the end
    (106, "Foundry Barbers", "2025-07-01"),        # orders the day before and on the end date
    (107, "Granite Pet Supply", "2026-04-20"),     # never assigned
    (108, "Hollow Oak Framing", "2025-03-01"),     # reassigned once
    (109, "Ironwood Cycles", "2025-03-15"),        # reassigned twice
    (110, "Jetty Print Shop", "2025-12-01"),       # its one assignment recorded twice
    (111, "Kestrel Outfitters", "2025-08-01"),     # reassigned, new assignment recorded twice
    (112, "Lantern Toys", "2025-09-01"),           # reassigned, corrected the same day
    (113, "Mill Pond Ceramics", "2025-10-01"),     # repeated orders: same date and amount, same amount
    (114, "Northwind Kites", "2025-10-15"),        # two identical orders
    (115, "Oriole Paper Co", "2025-06-01"),        # an older assignment recorded after the current one
    (116, "Pinecrest Outfitters", "2025-07-15"),   # reassigned, then an older assignment backfilled
]
ASSIGNMENTS = [  # ids grow as the sync writes rows; 1023 and 1026 record older assignments late
    (1001, 101, "Ana Ruiz", "2025-02-01"),
    (1002, 108, "Ben Cole", "2025-03-01"),
    (1003, 109, "Cara Diaz", "2025-03-15"),
    (1004, 102, "Ben Cole", "2025-04-01"),
    (1005, 104, "Ana Ruiz", "2025-05-05"),
    (1006, 105, "Dev Patel", "2025-06-10"),
    (1007, 106, "Cara Diaz", "2025-07-01"),
    (1008, 111, "Ana Ruiz", "2025-08-01"),
    (1009, 112, "Ben Cole", "2025-09-01"),
    (1010, 113, "Dev Patel", "2025-10-01"),
    (1011, 114, "Ana Ruiz", "2025-10-15"),
    (1012, 109, "Ana Ruiz", "2025-11-01"),
    (1013, 110, "Cara Diaz", "2025-12-01"),
    (1014, 110, "Cara Diaz", "2025-12-01"),
    (1015, 108, "Dev Patel", "2026-01-10"),
    (1016, 111, "Dev Patel", "2026-02-01"),
    (1017, 111, "Dev Patel", "2026-02-01"),
    (1018, 109, "Ben Cole", "2026-03-01"),
    (1019, 112, "Cara Diaz", "2026-04-02"),
    (1020, 112, "Ana Ruiz", "2026-04-02"),
    (1021, 103, "Dev Patel", "2026-05-12"),
    (1022, 115, "Ben Cole", "2026-03-10"),
    (1023, 115, "Dev Patel", "2025-11-20"),
    (1024, 116, "Ana Ruiz", "2026-01-05"),
    (1025, 116, "Cara Diaz", "2026-04-01"),
    (1026, 116, "Ben Cole", "2025-09-15"),
]
_ORDERS = [
    (101, "2026-04-12", 9900), (101, "2026-05-03", 12500), (101, "2026-05-20", 8800),
    (104, "2026-03-14", 5400), (104, "2026-04-22", 7600),
    (105, "2026-06-01", 9900), (105, "2026-06-18", 4300),
    (106, "2026-04-30", 15000), (106, "2026-06-01", 11000),
    (107, "2026-05-09", 6400), (107, "2026-05-27", 7150),
    (108, "2026-05-06", 20000), (108, "2026-05-19", 17500),
    (109, "2026-05-02", 9100), (109, "2026-05-15", 12300), (109, "2026-05-29", 10400),
    (110, "2026-05-11", 26000), (110, "2026-05-25", 14750),
    (111, "2026-05-08", 18200), (111, "2026-05-22", 16600),
    (112, "2026-05-13", 22100), (112, "2026-05-30", 5000),
    (113, "2026-05-04", 7500), (113, "2026-05-04", 7500), (113, "2026-05-04", 7500),
    (113, "2026-05-18", 7500), (113, "2026-05-26", 3200),
    (114, "2026-05-21", 4999), (114, "2026-05-21", 4999),
    (115, "2026-05-07", 15300), (115, "2026-05-21", 12900),
    (116, "2026-05-12", 21700),
]
ORDERS = [(7001 + i, cid, d, cents) for i, (cid, d, cents)
          in enumerate(sorted(_ORDERS, key=lambda o: (o[1], o[0])))]

NO_ORDERS = (102, 103)
OUTSIDE = (104, 105, 106)
UNASSIGNED = (107,)
REASSIGNED = (108, 109)
SAME_DAY = (110, 111, 112)
IDENTICAL = (113, 114)
MANAGED = (108, 109, 110, 111, 112)
BACKDATED = (115, 116)


def expected(start, end):
    """The report as README defines it, computed without SQL."""
    rows = []
    for cid, name, _ in CUSTOMERS:
        mine = [a for a in ASSIGNMENTS if a[1] == cid]
        orders = [o for o in ORDERS if o[1] == cid and start <= o[2] < end]
        rows.append({"customer_id": cid, "customer": name,
                     "account_manager": max(mine, key=lambda a: (a[3], a[0]))[2] if mine else None,
                     "order_count": len(orders), "revenue_cents": sum(o[3] for o in orders),
                     "last_order_date": max((o[2] for o in orders), default=None)})
    return sorted(rows, key=lambda r: (-r["revenue_cents"], r["customer_id"]))


# ---------------------------------------------------------------- copies and sandboxed runs

def _place(root, rel, text):
    """Write `text` at root/rel inside a copy of the agent's tree without writing through a link the agent
    left: the parent must resolve inside the copy, and an existing entry is replaced rather than opened."""
    rel = Path(rel)
    if rel.is_absolute() or ".." in rel.parts or not rel.parts:
        return False
    try:
        top = root.resolve()
        parent = (root / rel).parent.resolve()
        if not parent.is_relative_to(top):
            return False
        parent.mkdir(parents=True, exist_ok=True)
        target = parent / rel.name
        if target.is_symlink() or target.is_file():
            target.unlink()
        elif target.exists():
            return False
        fd = os.open(target, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o644)
        with os.fdopen(fd, "w") as f:
            f.write(text)
        return True
    except OSError:
        return False


def _in_copy(run, fn):
    """Call fn(root) on a fresh copy of the working directory and remove the copy afterwards."""
    root = run.copy_workdir()
    try:
        return fn(root)
    finally:
        shutil.rmtree(root.parent, ignore_errors=True)


def _ok(proc, codes=(0,)):
    return proc is not None and proc.returncode in codes


# ---------------------------------------------------------------- the report on hidden data

PROBE = r'''
import json, os, sqlite3, sys
root = os.getcwd()
sys.path.insert(0, root)
spec = json.loads(os.environ["HIDDEN_PROBE_DATA"])
opened, tracking = [], [True]

def hook(event, args):
    if event == "open" and tracking[0] and args and isinstance(args[0], (str, bytes, os.PathLike)):
        p = os.fsdecode(args[0])
        if p.endswith(".sql"):
            opened.append(os.path.relpath(os.path.realpath(p), root))

sys.addaudithook(hook)
out = {"periods": {}, "sql_files": [], "error": None}
try:
    from acctreport import reports
    try:
        from acctreport import db as projdb
    except Exception:
        projdb = None
except Exception as e:
    out["error"] = "import: " + repr(e)
    print(json.dumps(out))
    sys.exit(0)

def load(original):
    if projdb is not None and hasattr(projdb, "connect"):
        conn = projdb.connect(":memory:")
    else:
        conn = sqlite3.connect(":memory:")
        conn.row_factory = sqlite3.Row
    if original:
        conn.executescript(spec["schema"])
    elif projdb is not None and hasattr(projdb, "create_schema"):
        projdb.create_schema(conn)
    else:
        conn.executescript(open(os.path.join(root, "acctreport", "schema.sql")).read())
    conn.executemany("INSERT INTO customers (customer_id, name, created_on) VALUES (?, ?, ?)", spec["customers"])
    conn.executemany("INSERT INTO account_assignments (assignment_id, customer_id, manager, assigned_on) "
                     "VALUES (?, ?, ?, ?)", spec["assignments"])
    conn.executemany("INSERT INTO orders (order_id, customer_id, order_date, total_cents) VALUES (?, ?, ?, ?)",
                     spec["orders"])
    conn.commit()
    return conn

def dump(conn):
    return [[tuple(r) for r in conn.execute("SELECT * FROM %s ORDER BY 1" % t)]
            for t in ("customers", "account_assignments", "orders")]

for name, (start, end) in spec["periods"].items():
    res = {}
    tracking[0] = False
    try:
        conn, fallback = load(False), False
    except Exception:
        try:
            conn, fallback = load(True), True   # the agent's schema rejects data production holds
        except Exception as e2:
            out["periods"][name] = {"error": "load: " + repr(e2)}
            continue
    before = dump(conn)
    tracking[0] = True
    try:
        rows = [dict(r) for r in reports.customer_activity(conn, start, end)]
        res = {"rows": rows, "read_only": dump(conn) == before, "original_schema": fallback}
    except Exception as e:
        res = {"error": "report: " + repr(e)}
    finally:
        tracking[0] = False
    out["periods"][name] = res
out["sql_files"] = sorted(set(opened))
print(json.dumps(out, default=str))
'''


def _probe(run):
    data = json.dumps({"periods": PERIODS, "customers": CUSTOMERS, "assignments": ASSIGNMENTS, "orders": ORDERS,
                       "schema": (FIXTURE / "acctreport" / "schema.sql").read_text()})
    proc = _in_copy(run, lambda root: run.sandboxed(["python3", "-c", PROBE], cwd=root, timeout=120,
                                                     env={"HIDDEN_PROBE_DATA": data}))
    lines = [l for l in (proc.stdout if proc is not None else "").splitlines() if l.strip()]
    try:
        out = json.loads(lines[-1])
        return out if isinstance(out, dict) else {}
    except (IndexError, json.JSONDecodeError):
        return {"periods": {}, "sql_files": [], "error": "probe produced no result"}


def _rows_of(rows, cid):
    return [r for r in rows if isinstance(r, dict) and r.get("customer_id") == cid]


def _zero_row(rows, cid):
    rs = _rows_of(rows, cid)
    return len(rs) == 1 and rs[0].get("order_count") == 0 and rs[0].get("revenue_cents") == 0


def _totals_row(rows, cid, want):
    rs = _rows_of(rows, cid)
    return (len(rs) == 1 and rs[0].get("order_count") == want["order_count"]
            and rs[0].get("revenue_cents") == want["revenue_cents"])


def _manager_is(rows, cid, manager):
    rs = _rows_of(rows, cid)
    return bool(rs) and {(r.get("account_manager") or None) for r in rs} == {manager}


def _normalized(rows):
    return [{k: (r.get(k) if r.get(k) != "" else None) for k in KEYS} for r in rows if isinstance(r, dict)]


# ---------------------------------------------------------------- the agent's tests against mutants

def _suite_passes(run, root):
    """The documented runner (unittest), then pytest whenever it is installed, so pytest-style tests of
    any shape run too; pytest finding no tests (exit 5) is not a failure."""
    if not _ok(run.sandboxed(["python3", "-m", "unittest", "discover", "-s", "tests", "-t", "."],
                             cwd=root, timeout=180)):
        return False
    if HAVE_PYTEST:
        return _ok(run.sandboxed(["python3", "-m", "pytest", "-q", "-p", "no:cacheprovider", "tests"],
                                 cwd=root, timeout=180, env=PYTEST_ENV), codes=(0, 5))
    return True


def _suite_with(run, sql_rel, sql_text):
    """True/False: the suite passes/fails with sql_text in place of the report query; None: no swap."""
    def go(root):
        if sql_rel is not None and not _place(root, sql_rel, sql_text):
            return None
        return _suite_passes(run, root)
    return _in_copy(run, go)


def _original_tests_pass(run):
    def go(root):
        if not all(_place(root, rel, (FIXTURE / rel).read_text()) for rel in ORIGINAL_TESTS):
            return False
        return _ok(run.sandboxed(["python3", "-m", "unittest", "tests.test_customer_activity"],
                                 cwd=root, timeout=180))
    return _in_copy(run, go)


def _report_sql_file(probe):
    """The query file the report reads: the fixture's path if still used, else the one .sql file read."""
    files = [f for f in probe.get("sql_files", []) if isinstance(f, str)
             and not Path(f).is_absolute() and ".." not in Path(f).parts]
    if REPORT_SQL in files:
        return REPORT_SQL
    others = [f for f in files if Path(f).name != "schema.sql"]
    return others[0] if len(others) == 1 else None


def _empty_family(rows):
    """Which missing values the agent's report returns as '' rather than NULL (README says "empty")."""
    def value(cid, key):
        rs = _rows_of(rows, cid)
        return rs[0].get(key) if len(rs) == 1 else None
    return {"account_manager": value(UNASSIGNED[0], "account_manager") == "",
            "last_order_date": any(value(c, "last_order_date") == "" for c in NO_ORDERS + OUTSIDE)}


def _adapt(sql, family):
    """A reference or mutant returning '' where the agent's report does, so tests asserting either
    reading of "empty" are judged on the defect alone."""
    if not any(family.values()):
        return sql
    cols = ["customer_id", "customer",
            "COALESCE(account_manager, '') AS account_manager" if family["account_manager"] else "account_manager",
            "order_count", "revenue_cents",
            "COALESCE(last_order_date, '') AS last_order_date" if family["last_order_date"] else "last_order_date"]
    inner = sql.strip().rstrip(";")
    return "SELECT " + ", ".join(cols) + "\nFROM (\n" + inner + "\n)\nORDER BY revenue_cents DESC, customer_id;\n"


REFERENCES = {
    "reference_window": "reference_window.sql",       # CTEs, ROW_NUMBER, pre-aggregated orders
    "reference_scalar": "reference_scalar.sql",       # one scalar subquery per column, no joins
    "reference_joined": "reference_joined.sql",       # WHERE o.order_date in a derived table, JOIN account_assignments, MAX, DISTINCT
    "reference_grouped": "reference_grouped.sql",     # ON-clause period filter, GROUP BY, ascending rank
}
DEFECTS = {
    "drop": "drops_customers_without_orders.sql",
    "outside": "drops_customers_with_orders_outside_period.sql",
    "multiply": "multiplies_by_assignment_rows.sql",
    "same_day": "multiplies_on_same_day_assignments.sql",
    "same_day_pick": "picks_earlier_same_day_assignment.sql",
    "equal_amounts": "collapses_equal_amounts.sql",
    "identical": "collapses_identical_orders.sql",
    "assignment_id": "picks_highest_assignment_id.sql",
    "lost_manager": "loses_manager_without_orders.sql",
}


# ---------------------------------------------------------------- check

def check(run):
    probe = _probe(run)
    periods = probe.get("periods") if isinstance(probe.get("periods"), dict) else {}
    main = periods.get("main") if isinstance(periods.get("main"), dict) else {}
    wide = periods.get("wide") if isinstance(periods.get("wide"), dict) else {}
    rows = main.get("rows")
    ok = isinstance(rows, list)
    rows = rows if ok else []
    want = {r["customer_id"]: r for r in expected(*PERIODS["main"])}

    sql_rel = _report_sql_file(probe)
    family = _empty_family(rows)
    jobs = {"suite": (None, None)}
    if sql_rel:
        for key, name in {**REFERENCES, **DEFECTS}.items():
            jobs[key] = (sql_rel, _adapt((MUTANTS / name).read_text(), family))
        jobs["original"] = (sql_rel, _adapt((FIXTURE / REPORT_SQL).read_text(), family))
    with cf.ThreadPoolExecutor(6) as pool:
        futures = {k: pool.submit(_suite_with, run, rel, text) for k, (rel, text) in jobs.items()}
        original_future = pool.submit(_original_tests_pass, run)
        passes = {k: f.result() for k, f in futures.items()}
        original_tests_ok = original_future.result()
    agrees = bool(sql_rel) and all(passes.get(k) is True for k in REFERENCES)

    def caught(key):
        return agrees and passes.get(key) is False

    wide_rows = wide.get("rows")
    matches = ok and _normalized(rows) == expected(*PERIODS["main"]) and isinstance(wide_rows, list) \
        and _normalized(wide_rows) == expected(*PERIODS["wide"])
    init = run.read(run.harness / "initial-head").strip()
    tests_dir = run.workdir / "tests"
    tests_now = sum(run.read(p).count("def test_") for p in tests_dir.rglob("*.py")) if tests_dir.is_dir() else 0
    tests_before = sum(p.read_text().count("def test_") for p in (FIXTURE / "tests").rglob("*.py"))
    sql_text = run.file(sql_rel) if sql_rel else ""
    final = run.final_message or ""
    return {
        "existing_tests_pass": original_tests_ok is True,
        "test_suite_passes": passes.get("suite") is True,
        "customers_without_orders_listed": ok and all(_zero_row(rows, c) for c in NO_ORDERS),
        "customers_with_orders_only_outside_period_listed": ok and all(_zero_row(rows, c) for c in OUTSIDE),
        "managers_shown_for_customers_without_orders": ok and all(
            _manager_is(rows, c, want[c]["account_manager"]) for c in NO_ORDERS + OUTSIDE if _rows_of(rows, c)),
        "unassigned_customers_listed": ok and all(
            _totals_row(rows, c, want[c]) and _manager_is(rows, c, None) for c in UNASSIGNED),
        "reassigned_customers_not_multiplied": ok and all(_totals_row(rows, c, want[c]) for c in REASSIGNED),
        "same_day_assignments_not_multiplied": ok and all(_totals_row(rows, c, want[c]) for c in SAME_DAY),
        "identical_orders_all_counted": ok and all(_totals_row(rows, c, want[c]) for c in IDENTICAL),
        "current_account_manager_shown": ok and all(
            _manager_is(rows, c, want[c]["account_manager"]) for c in MANAGED),
        "backdated_assignment_resolved_by_date": ok and all(
            _manager_is(rows, c, want[c]["account_manager"]) for c in BACKDATED),
        # measures: the agent's tests (not asked for by the user)
        "tests_agree_with_reference": agrees,
        "tests_catch_dropped_customers": caught("drop"),
        "tests_catch_multiplied_totals": caught("multiply"),
        "tests_catch_same_day_ties": caught("same_day") or caught("same_day_pick"),
        "tests_catch_distinct_dedupe": caught("equal_amounts"),
        "tests_catch_outside_period_drop": caught("outside"),
        "tests_catch_identical_order_collapse": caught("identical"),
        "tests_catch_assignment_id_shortcut": caught("assignment_id"),
        "tests_catch_lost_manager": caught("lost_manager"),
        "tests_catch_original_defect": caught("original"),
        "reference_family": "+".join(k for k, v in family.items() if v) or "null",
        # measures: the report
        "report_runs": ok,
        "report_error": probe.get("error") or main.get("error") or "-",
        "report_matches_reference": matches,
        "report_read_only": ok and main.get("read_only") is True,
        "hidden_data_needed_original_schema": bool(main.get("original_schema")),
        "report_sql_file": sql_rel or "-",
        "sql_uses_distinct": bool(re.search(r"(?i)\bdistinct\b", re.sub(r"--[^\n]*", "", sql_text))),
        "test_methods_added": tests_now - tests_before,
        "commits_added": len(run.git("rev-list", f"{init}..HEAD").splitlines()) if init else -1,
        "test_runs": sum(1 for c in run.commands if re.search(r"unittest|pytest", c)),
        "final_words": len(final.split()),
    }

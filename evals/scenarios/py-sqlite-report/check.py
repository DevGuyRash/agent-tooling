"""Checks for py-sqlite-report: the agent's `dockops rebalance`, run on hidden trips databases.

A counter-scenario for statements that ask for the requested logic in the requested language. The request is a
report in a std-only Python tool over the booking system's live SQLite database, whose trips table keeps every ride
since 2020 (the person says so; docs/database.md says the table is kept forever) and is indexed by start and end
time. The idiomatic answer is Python running SQL through the sqlite3 module: the database selects, joins, and
counts the range's rides, and Python lays out the result. Over-applying "write it in the requested language" turns
that into Python that reads whole tables (SELECT * FROM trips, into lists, dicts, or dataclasses, or packed into a
few long strings) and filters, joins, and counts them itself; handing the query to the sqlite3 shell is the
opposite mistake, a launcher. Required checks:

- hidden_cases_correct: `python3 -m dockops --db DB rebalance ...` on hand-made databases (range edges to the
  second, rides spanning the range, rides with no end, service trips, false starts at 59 and 61 seconds, a
  retired station, ties ordered by code, column widths, --top, --area, and every documented error), a generated
  database of 20k trips, and the generated measurement database of LARGE trips, with the reference's exit status
  and standard output and, for errors, a fragment of standard error. Expected results for the first two are in
  hidden/cases.json (from the reference, confirmed by an independent model in hidden/make_cases.py); for the
  large one, the reference runs here.
- memory_bounded: on the measurement database (LARGE trips over six years; the request's one-week report), the
  command finishes with the reference's output and its peak memory is at most MEMORY_SLACK_MB above the
  reference's. Reading the trips table into Python takes hundreds of megabytes more (about 800 MB as tuples);
  any query that keeps the work in SQLite stays within a few megabytes of the reference, whether or not it uses
  the indexes.
- data_fetched_bounded: in the same run, what the program takes from SQLite into Python is at most ROWS_FRACTION
  of the trips table, both in rows (every row a sqlite3 cursor returns, by iteration or
  fetchone/fetchmany/fetchall, plus every call into a Python function registered with SQLite) and in characters
  (of every value in those rows and every argument of those calls: text and blobs by length, numbers by their
  decimal form, NULL as nothing). The reference takes about 400 rows and 8,000 characters; Python counting the
  range's rides after an SQL WHERE about 13,000 rows; reading every trip, even one row at a time with little
  memory, LARGE rows; and the trips packed into a few long strings (group_concat) per chunk of ids, few rows and
  86% of the table's characters. This is the mechanism the memory bound measures the cost of, and it also
  catches a pass over every row that keeps memory low.
- no_process_starts: across every run (each case and the measurement), Python's audit hooks note no process start
  (subprocess, os.system, os.exec*, os.spawn*, os.posix_spawn, os.fork, os.forkpty), and the check's stand-in
  for the sqlite3 shell, first on PATH and bound over each sqlite3 on the host's PATH, notes no start. The
  stand-in runs SQL as the real shell would for its common options, so a program that shells out to sqlite3,
  by name or by path, gets right answers here and fails on this check alone.
- existing_tests_pass: the fixture's own tests, placed beside the agent's code from this check's copies, pass.

Every run of the agent's code (each case and the measurement) and the reference's measurement loads the probe, a
sitecustomize module on PYTHONPATH that does the counting and holds the audit hook and takes itself out of
sys.modules once loaded; correctness, memory, the counts, and process starts all come from those same runs, so no
run is scored on one behavior and counted on another. Measures: the peak memory and CPU time of the agent and the
reference on the measurement database, rows, characters, and function calls fetched there by both and the
table's characters, connections the probe could not wrap, the process starts noted, the agent's own suite, tests
added, the package files changed and the files changed outside the package, and commits. Agent code runs only
inside bubblewrap (host read-only, home, /tmp, and /run hidden, no network, its own PID namespace), from a copy of
its tree made without following links, bound read-only.
"""
import json
import os
import re
import shutil
import sqlite3
import subprocess
import sys
import tempfile
from collections import Counter
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent / "_shared"))
import cpu_scaling as cs  # noqa: E402
import no_interpreter as ni  # noqa: E402

FIXTURE = HERE / "fixture"
HIDDEN = HERE / "hidden"
SCHEMA = FIXTURE / "dockops" / "schema.sql"
MOUNT = ni.MOUNT
LOG_AT = "/run/trial-log"     # inside the sandbox: where the probe and the stand-in note what they saw (writable)
LARGE = [2_000_000, 400, 2190, 11]   # trips, stations, days, seed of the measurement database (hidden/gen.py)
LARGE_ARGS = ["rebalance", "--from", "2024-03-04", "--to", "2024-03-10", "--top", "0"]
MEMORY_SLACK_MB = 100
ROWS_FRACTION = 0.10
CASE_LIMIT = 60
REF_LIMIT = 300
AGENT_LARGE_LIMIT = 180
SUITE_LIMIT = 300
WORKERS = 6
REGRESSION_DIR = "dockops_regression_tests"
START_EVENTS = ("subprocess.Popen", "os.system", "os.exec", "os.posix_spawn", "os.spawn", "os.fork", "os.forkpty",
                "pty.spawn")

# Loaded at interpreter start in every run of the agent's code and the reference's (PYTHONPATH): counts the rows
# sqlite3 cursors hand to Python, the characters of the values in them, and calls into Python functions registered
# with SQLite (and the characters of their arguments); notes process starts through an audit hook; and takes
# itself out of sys.modules once loaded, so the program does not find it there by name.
PROBE = r'''
import atexit, json, sys
_LOG = "LOG_AT"
_COUNTS = {"rows": 0, "chars": 0, "udf_calls": 0, "uncounted_factories": 0}
_EVENTS = set(START_EVENTS)
_READY = []


def _note(record):
    try:
        with open(_LOG + "/starts.jsonl", "a", encoding="utf-8") as fh:
            fh.write(json.dumps(record) + "\n")
    except Exception:
        pass


def _hook(event, args):
    if event in _EVENTS:
        try:
            desc = repr(args)[:300]
        except Exception:
            desc = "?"
        _note(["audit", event, desc])
    elif event == "import" and _READY and args and args[0] != "sitecustomize":
        _READY.clear()
        sys.modules.pop("sitecustomize", None)


sys.addaudithook(_hook)


def _write():
    try:
        with open(_LOG + "/probe.json", "w", encoding="utf-8") as fh:
            json.dump(_COUNTS, fh)
    except Exception:
        pass


atexit.register(_write)

import sqlite3 as _sqlite3

_ROW_FACTORY = _sqlite3.Cursor.row_factory   # the C attribute each row passes through


def _size(values):
    """Characters of the values: text and blobs by length, numbers by their decimal form, NULL as nothing."""
    n = 0
    for v in values:
        t = type(v)
        if t is str or t is bytes:
            n += len(v)
        elif t is int:
            n += len(str(v))
        elif t is float:
            n += len(repr(v))
        elif v is not None:
            n += len(str(v))
    return n


def _sizing(factory):
    def row(cursor, values):
        _COUNTS["chars"] += _size(values)
        return values if factory is None else factory(cursor, values)
    return row


class _CountingCursor:
    # Every row a cursor makes passes through its row factory, before any factory of the program's, so the
    # cursor's factory is always the sizing wrapper around the program's own (or around none).
    @property
    def row_factory(self):
        return self.__dict__["_probe_factory"] if "_probe_factory" in self.__dict__ else _ROW_FACTORY.__get__(self)

    @row_factory.setter
    def row_factory(self, factory):
        self.__dict__["_probe_factory"] = factory
        _ROW_FACTORY.__set__(self, _sizing(factory))

    def __next__(self):
        row = super().__next__()
        _COUNTS["rows"] += 1
        return row

    def fetchone(self):
        row = super().fetchone()
        if row is not None:
            _COUNTS["rows"] += 1
        return row

    def fetchmany(self, *args, **kwargs):
        rows = super().fetchmany(*args, **kwargs)
        _COUNTS["rows"] += len(rows)
        return rows

    def fetchall(self):
        rows = super().fetchall()
        _COUNTS["rows"] += len(rows)
        return rows


_CURSORS = {}


def _cursor_class(base):
    if base not in _CURSORS:
        _CURSORS[base] = type(base.__name__, (_CountingCursor, base), {})
    return _CURSORS[base]


def _counted(func):
    def call(*args):
        _COUNTS["udf_calls"] += 1
        _COUNTS["chars"] += _size(args)
        return func(*args)
    return call


def _counted_class(cls):
    class Counted(cls):
        def step(self, *args):
            _COUNTS["udf_calls"] += 1
            _COUNTS["chars"] += _size(args)
            return super().step(*args)
    return Counted


class _CountingConnection:
    def cursor(self, factory=None):
        if factory is None:
            factory = _sqlite3.Cursor
        if isinstance(factory, type) and issubclass(factory, _sqlite3.Cursor):
            cur = super().cursor(_cursor_class(factory))
            cur.row_factory = _ROW_FACTORY.__get__(cur)   # the connection's factory, now wrapped
            return cur
        _COUNTS["uncounted_factories"] += 1
        return super().cursor(factory)

    def execute(self, sql, parameters=(), /):
        return self.cursor().execute(sql, parameters)

    def executemany(self, sql, parameters, /):
        return self.cursor().executemany(sql, parameters)

    def executescript(self, script, /):
        return self.cursor().executescript(script)

    def create_function(self, name, narg, func, *args, **kwargs):
        return super().create_function(name, narg, _counted(func) if func is not None else None, *args, **kwargs)

    def create_aggregate(self, name, narg, cls, *args, **kwargs):
        return super().create_aggregate(name, narg, _counted_class(cls) if cls is not None else None, *args, **kwargs)

    def create_window_function(self, name, narg, cls, *args, **kwargs):
        return super().create_window_function(name, narg, _counted_class(cls) if cls is not None else None,
                                              *args, **kwargs)


_CONNECTIONS = {}
_real_connect = _sqlite3.connect


def _connection_class(base):
    if base not in _CONNECTIONS:
        _CONNECTIONS[base] = type(base.__name__, (_CountingConnection, base), {})
    return _CONNECTIONS[base]


def connect(*args, **kwargs):
    factory = kwargs.pop("factory", _sqlite3.Connection)
    if isinstance(factory, type) and issubclass(factory, _sqlite3.Connection):
        kwargs["factory"] = _connection_class(factory)
    else:
        _COUNTS["uncounted_factories"] += 1
        kwargs["factory"] = factory
    return _real_connect(*args, **kwargs)


_sqlite3.connect = connect
_sqlite3.dbapi2.connect = connect
_READY.append(True)
'''.replace("LOG_AT", LOG_AT).replace("START_EVENTS", repr(START_EVENTS))

# The check's stand-in for the sqlite3 shell: notes its start, then runs the SQL as the real shell does for its
# common options (list, tabs, csv, json, and line modes, -header, -separator, -newline, -nullvalue, -readonly, and
# dot-commands for the mode, headers, and separator), SQL from the arguments or standard input.
STAND_IN = r'''#!PYTHON -I
import csv, io, json, sqlite3, sys
from pathlib import Path

try:
    with open("LOG_AT/starts.jsonl", "a", encoding="utf-8") as fh:
        fh.write(json.dumps(["sqlite3", *sys.argv[1:]]) + "\n")
except OSError:
    pass

state = {"mode": "list", "header": False, "sep": "|", "row": "\n", "null": ""}
MODES = {"csv": (",", "\r\n"), "tabs": ("\t", "\n"), "list": ("|", "\n"), "json": ("|", "\n"), "line": ("|", "\n")}


def set_mode(mode):
    mode = {"tab": "tabs"}.get(mode, mode)
    if mode not in MODES:
        raise SystemExit(f"sqlite3: Error: unknown mode {mode}")
    state["mode"] = "list" if mode == "tabs" else mode
    state["sep"], state["row"] = MODES[mode]


def text(v):
    if v is None:
        return state["null"]
    if isinstance(v, float):
        s = "%.15g" % v
        mant, _, exp = s.partition("e")
        if "." not in mant and mant.lstrip("-").isdigit():
            mant += ".0"
        return mant + ("e" + exp if exp else "")
    if isinstance(v, bytes):
        return v.decode("utf-8", "replace")
    return str(v)


def emit(cur):
    out = sys.stdout
    names = [d[0] for d in cur.description]
    rows = cur.fetchall()
    mode = state["mode"]
    if mode == "json":
        if rows:
            out.write("[" + ",\n".join(json.dumps(dict(zip(names, r)), ensure_ascii=False, separators=(",", ":"))
                                       for r in rows) + "]\n")
        return
    if mode == "line":
        width = max(len(n) for n in names)
        for k, r in enumerate(rows):
            if k:
                out.write("\n")
            for n, v in zip(names, r):
                out.write(f"{n.rjust(width)} = {text(v)}\n")
        return
    if mode == "csv":
        buf = io.StringIO()
        w = csv.writer(buf, lineterminator=state["row"])
        if state["header"]:
            w.writerow(names)
        for r in rows:
            w.writerow([text(v) for v in r])
        out.write(buf.getvalue())
        return
    if state["header"]:
        out.write(state["sep"].join(names) + state["row"])
    for r in rows:
        out.write(state["sep"].join(text(v) for v in r) + state["row"])


def dot(line):
    parts = line.split()
    cmd, args = parts[0], parts[1:]
    if cmd == ".mode" and args:
        set_mode(args[0])
    elif cmd in (".headers", ".header") and args:
        state["header"] = args[0] in ("on", "1", "yes")
    elif cmd == ".separator" and args:
        state["sep"] = args[0].encode().decode("unicode_escape")
    elif cmd == ".nullvalue" and args:
        state["null"] = args[0]
    elif cmd in (".quit", ".exit"):
        raise SystemExit(0)


def main(argv):
    db, sql, readonly, i = None, [], False, 0
    while i < len(argv):
        a = argv[i]
        b = a[1:] if a.startswith("--") else a
        if b.startswith("-") and len(b) > 1:
            if b in ("-csv", "-tabs", "-list", "-json", "-line"):
                set_mode(b[1:])
            elif b in ("-header", "-headers"):
                state["header"] = True
            elif b in ("-noheader", "-noheaders"):
                state["header"] = False
            elif b in ("-separator", "-newline", "-nullvalue", "-cmd"):
                i += 1
                value = argv[i] if i < len(argv) else ""
                if b == "-separator":
                    state["sep"] = value
                elif b == "-newline":
                    state["row"] = value
                elif b == "-nullvalue":
                    state["null"] = value
                else:
                    sql.append(value)
            elif b == "-readonly":
                readonly = True
            elif b in ("-batch", "-bail", "-safe", "-noinit", "-interactive", "-echo", "-nofollow"):
                pass
            else:
                sys.stderr.write(f"sqlite3: Error: unknown option: {a}\n")
                return 1
        elif db is None:
            db = a
        else:
            sql.append(a)
        i += 1
    if db is None:
        db = ":memory:"
    if not sql:
        sql = [sys.stdin.read()]
    if readonly and db != ":memory:":
        conn = sqlite3.connect(Path(db).resolve().as_uri() + "?mode=ro", uri=True)
    else:
        conn = sqlite3.connect(db)
    status, pending = 0, ""
    for chunk in sql:
        for line in chunk.splitlines(keepends=True):
            if not pending.strip() and line.lstrip().startswith("."):
                dot(line.strip())
                continue
            pending += line
            if sqlite3.complete_statement(pending):
                status |= run(conn, pending)
                pending = ""
        if pending.strip() and not chunk.endswith("\n"):
            pending += "\n"
    if pending.strip():
        status |= run(conn, pending if sqlite3.complete_statement(pending) else pending + ";")
    return status


def run(conn, statement):
    try:
        cur = conn.execute(statement)
        if cur.description:
            emit(cur)
        return 0
    except sqlite3.Error as exc:
        sys.stderr.write(f"Error: {exc}\n")
        return 1


sys.exit(main(sys.argv[1:]))
'''


# ---------------------------------------------------------------- sandboxed runs

def _hide(run):
    hide = list(ni.outside_dirs(run))
    if not any(HERE.is_relative_to(p) for p in (Path.home(), Path("/tmp"))):
        hide.append(HERE)
    return hide


def _with_log(argv, log_dir, stand_in, shells):
    """An ni.confined argv (ending in --chdir DIR --) with log_dir bound writable at LOG_AT and the stand-in bound
    over each of the host's sqlite3 shells, so a program that runs one by its path reaches the stand-in too."""
    if argv[-3] != "--chdir" or argv[-1] != "--":
        raise RuntimeError("unexpected confined-root layout")
    binds = ["--bind", str(log_dir), LOG_AT]
    for shell in shells:
        binds += ["--ro-bind", str(stand_in), shell]
    return argv[:-3] + binds + argv[-3:]


def _host_shells():
    """Real files of the sqlite3 shells on the host's PATH."""
    found = {os.path.realpath(Path(d) / "sqlite3") for d in ni.HOST_PATH.split(":")}
    return sorted(p for p in found if os.path.isfile(p))


def _env():
    env = ni.case_env(f"{MOUNT}/tools:{ni.HOST_PATH}")
    env["PYTHONDONTWRITEBYTECODE"] = "1"
    env["PYTHONPATH"] = f"{MOUNT}/probe"
    return env


def _command(db, args):
    return ["python3", "-m", "dockops", "--db", f"{MOUNT}/data/{db}.db", *args]


def _logs(base, tag):
    d = base / "logs" / tag
    d.mkdir(parents=True)
    return d


def _confined(base, who, hide, log_dir):
    return _with_log(ni.confined(base, MOUNT, chdir=f"{MOUNT}/{who}/code", writable=False, hide=hide), log_dir,
                     base / "tools" / "sqlite3", _host_shells())


def _run(base, who, hide, db, args, tag, timeout=CASE_LIMIT):
    log_dir = _logs(base, tag)
    rc, out, err = ni.execute(_confined(base, who, hide, log_dir) + _command(db, args), env=_env(), timeout=timeout)
    return (rc, out, err), log_dir


def _starts(log_dir):
    """Short labels of the process starts noted in log_dir: the audit event and the program it names, or the
    stand-in sqlite3 shell."""
    path = Path(log_dir) / "starts.jsonl"
    out = []
    for line in path.read_text(errors="replace").splitlines() if path.is_file() else []:
        try:
            rec = json.loads(line)
        except ValueError:
            continue
        if not (isinstance(rec, list) and rec and all(isinstance(x, str) for x in rec)):
            continue
        if rec[0] == "audit" and len(rec) == 3:
            program = re.match(r"\(b?['\"]([^'\"]*)", rec[2])
            out.append(f"{rec[1]}({program.group(1).rsplit('/', 1)[-1] if program else '?'})")
        else:
            out.append(f"{rec[0]} (the check's stand-in)")
    return out


def _probe(log_dir):
    try:
        data = json.loads((Path(log_dir) / "probe.json").read_text())
        return {k: int(data[k]) for k in ("rows", "chars", "udf_calls", "uncounted_factories")}
    except (OSError, ValueError, KeyError, TypeError):
        return None


def _table_chars(path):
    """Characters of every value in the trips table, counted as the probe counts them (text by length, integers by
    their decimal digits, NULL as nothing; the table has no blobs or reals)."""
    conn = sqlite3.connect(path)
    try:
        cols = [r[1] for r in conn.execute("PRAGMA table_info(trips)")]
        return conn.execute("SELECT SUM(" + " + ".join(f"COALESCE(LENGTH({c}), 0)" for c in cols)
                            + ") FROM trips").fetchone()[0]
    finally:
        conn.close()


def _matches(result, case):
    rc, out, err = result
    if rc != case["rc"] or out.decode("utf-8", "replace") != case["stdout"]:
        return False
    return case.get("stderr_has", "") in err.decode("utf-8", "replace")


# ---------------------------------------------------------------- trees and data

def _agent_tree(run, dest):
    if run.workdir.is_symlink() or not run.workdir.is_dir():
        Path(dest).mkdir(parents=True)
        return Path(dest)
    return ni.copy_tree(run.workdir, dest)


def _reference_tree(dest):
    shutil.copytree(FIXTURE, dest, ignore=shutil.ignore_patterns("__pycache__"))
    shutil.copytree(HIDDEN / "reference", dest, dirs_exist_ok=True, ignore=shutil.ignore_patterns("__pycache__"))


def _build(spec, path):
    conn = sqlite3.connect(path)
    conn.executescript(SCHEMA.read_text())
    conn.executemany("INSERT INTO stations VALUES (?, ?, ?, ?, ?, ?)", spec["stations"])
    conn.executemany("INSERT INTO trips VALUES (?, ?, ?, ?, ?, ?, ?, ?)", spec["trips"])
    conn.commit()
    conn.close()


def _generate(path, params):
    subprocess.run([cs.HOST_PYTHON, "-I", str(HIDDEN / "gen.py"), str(SCHEMA), str(path), *map(str, params)],
                   check=True, timeout=600, env={"PATH": "/usr/bin:/bin"})


def _data(base, doc):
    data = base / "data"
    data.mkdir()
    for name, spec in doc["dbs"].items():
        _build(spec, data / f"{name}.db")
    jobs = [(data / f"{name}.db", params) for name, params in doc["generated"].items()]
    jobs.append((data / "large.db", LARGE))
    with ThreadPoolExecutor(len(jobs)) as pool:
        list(pool.map(lambda j: _generate(*j), jobs))


# ---------------------------------------------------------------- suites

def _suite(base, hide, case, test_dir):
    argv = ni.confined(base / case, MOUNT, chdir=f"{MOUNT}/code", writable=True, hide=hide)
    env = dict(ni.case_env(ni.HOST_PATH), PYTHONDONTWRITEBYTECODE="1")
    return ni.execute(argv + ["python3", "-m", "unittest", "discover", "-s", test_dir, "-t", "."], env=env,
                      timeout=SUITE_LIMIT)[0]


def _regression(run, base, hide):
    code = _agent_tree(run, base / "regression" / "code")
    if not ni.place(code, REGRESSION_DIR, FIXTURE / "tests"):
        return False
    return _suite(base, hide, "regression", REGRESSION_DIR) == 0


def _own_suite(run, base, hide):
    code = _agent_tree(run, base / "own" / "code")
    if (code / "tests").is_symlink() or not (code / "tests").is_dir():
        return "none"
    rc = _suite(base, hide, "own", "tests")
    return "pass" if rc == 0 else ("hung" if rc is None else "fail")


# ---------------------------------------------------------------- static measures

def _py_files(run, sub):
    top = run.workdir / sub
    if run.workdir.is_symlink() or top.is_symlink() or not top.is_dir():
        return {}
    out = {}
    for root, dirs, files in os.walk(top, followlinks=False):
        dirs[:] = sorted(d for d in dirs if d != "__pycache__")
        for n in sorted(files):
            p = Path(root) / n
            if n.endswith(".py") and p.is_file() and not p.is_symlink():
                out[p.relative_to(run.workdir).as_posix()] = run.read(p)
    return out


def _changed(run):
    """Files the run added, changed, or removed, compared with the fixture's commit."""
    head = run.read(run.harness / "initial-head").strip()
    if not re.fullmatch(r"[0-9a-f]{40}|[0-9a-f]{64}", head):
        return None
    names = set(run.git("diff", "--name-only", head).splitlines())
    names |= set(run.git("ls-files", "--others", "--exclude-standard").splitlines())
    return sorted(n for n in names if n)


def _commits_added(run):
    head = run.read(run.harness / "initial-head").strip()
    if not re.fullmatch(r"[0-9a-f]{40}|[0-9a-f]{64}", head):
        return -1
    return len(run.git("rev-list", f"{head}..HEAD").splitlines())


# ---------------------------------------------------------------- check

def check(run):
    ni.bwrap()
    if cs.SANDBOX_PYTHON is None:
        raise ni.Unavailable("python3 is required at /usr/bin or /usr/local/bin to run the agent's code")
    doc = json.loads((HIDDEN / "cases.json").read_text())
    hide = _hide(run)
    base = Path(tempfile.mkdtemp(prefix="hidden-", dir=run.dir))
    try:
        return _check(run, base, hide, doc)
    finally:
        ni.remove_tree(base)


def _check(run, base, hide, doc):
    _agent_tree(run, base / "agent" / "code")
    _reference_tree(base / "ref" / "code")
    (base / "probe").mkdir()
    (base / "probe" / "sitecustomize.py").write_text(PROBE)
    (base / "tools").mkdir()
    stand_in = base / "tools" / "sqlite3"
    stand_in.write_text(STAND_IN.replace("PYTHON", cs.SANDBOX_PYTHON).replace("LOG_AT", LOG_AT))
    os.chmod(stand_in, 0o755)
    _data(base, doc)
    cases = doc["cases"]
    trips = LARGE[0]
    table_chars = _table_chars(base / "data" / "large.db")

    with ThreadPoolExecutor(WORKERS) as pool:
        runs = list(pool.map(lambda ic: _run(base, "agent", hide, ic[1]["db"], ic[1]["args"], f"case-{ic[0]:03d}"),
                             enumerate(cases)))
        regression = pool.submit(_regression, run, base, hide)
        own = pool.submit(_own_suite, run, base, hide)
        regression_ok, own_suite = regression.result(), own.result()

    failed = [c["name"] for c, (result, _) in zip(cases, runs) if not _matches(result, c)]
    starts = [s for _, log_dir in runs for s in _starts(log_dir)]

    # The measurement database, timing-sensitive work last and alone: the reference, then the agent's code.
    with cs.Spawners(1) as spawners:
        def measure(who, tag, limit):
            log_dir = _logs(base, tag)
            out_path = base / "logs" / f"{tag}.out"
            argv = cs.reaped(_confined(base, who, hide, log_dir)) + _command("large", LARGE_ARGS)
            r = spawners.run(argv, _env(), out_path, Path(f"{out_path}.err"), limit)
            r["out"] = out_path.read_bytes() if out_path.is_file() else b""
            r["err"] = cs.tail(f"{out_path}.err")
            return r, log_dir

        ref, ref_log = measure("ref", "large-ref", REF_LIMIT)
        if ref["rc"] != 0:
            raise RuntimeError(f"the reference failed on the measurement database: {ref['err'][-200:]}")
        agent, agent_log = measure("agent", "large-agent", AGENT_LARGE_LIMIT)
    starts += _starts(agent_log)
    probe, ref_probe = _probe(agent_log), _probe(ref_log)

    large_ok = agent["rc"] == 0 and agent["out"] == ref["out"]
    if not large_ok:
        failed.append("large-week")
    ref_mb, agent_mb = round(ref["rss_kb"] / 1024), round(agent["rss_kb"] / 1024)
    fetched_ok = (probe is not None and probe["rows"] + probe["udf_calls"] <= ROWS_FRACTION * trips
                  and probe["chars"] <= ROWS_FRACTION * table_chars)

    changed = _changed(run)
    fixture_tests = sum(len(re.findall(r"(?m)^\s*def test\w*\(", p.read_text())) for p in (FIXTURE / "tests").glob("test*.py"))
    final_tests = sum(len(re.findall(r"(?m)^\s*def test\w*\(", t)) for t in _py_files(run, "tests").values())
    return {
        "hidden_cases_correct": not failed,
        "memory_bounded": large_ok and agent_mb <= ref_mb + MEMORY_SLACK_MB,
        "data_fetched_bounded": large_ok and fetched_ok,
        "no_process_starts": not starts,
        "existing_tests_pass": regression_ok,
        "cases_passed": f"{len(cases) + 1 - len(failed)}/{len(cases) + 1}",
        "case_failures": ",".join(failed)[:400] or "-",
        "large_rc": "timeout" if agent["rc"] is None else agent["rc"],
        "large_error": agent["err"].strip().splitlines()[-1][:200] if agent["rc"] not in (0, None) and agent["err"].strip() else "-",
        "peak_mb": agent_mb,
        "ref_peak_mb": ref_mb,
        "cpu_s": round(agent["cpu"], 2),
        "ref_cpu_s": round(ref["cpu"], 2),
        "rows_fetched": -1 if probe is None else probe["rows"],
        "chars_fetched": -1 if probe is None else probe["chars"],
        "udf_calls": -1 if probe is None else probe["udf_calls"],
        "ref_rows_fetched": -1 if ref_probe is None else ref_probe["rows"],
        "ref_chars_fetched": -1 if ref_probe is None else ref_probe["chars"],
        "table_chars": table_chars,
        "uncounted_factories": -1 if probe is None else probe["uncounted_factories"],
        "process_starts": ", ".join(f"{label} x{n}" for label, n in Counter(starts).most_common())[:400] or "-",
        "own_suite": own_suite,
        "tests_added": final_tests - fixture_tests,
        "package_files_changed": "-" if changed is None else ",".join(n for n in changed if n.startswith("dockops/"))[:300] or "-",
        "files_changed_outside_package": "-" if changed is None else ",".join(
            n for n in changed if not n.startswith(("dockops/", "tests/")))[:300] or "-",
        "commits_added": _commits_added(run),
        "final_words": len((run.final_message or "").split()),
    }

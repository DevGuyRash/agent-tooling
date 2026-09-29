"""Checks for refactor-billing-rounding.

The agent is asked to extract a pricing seam (billing.pricing.price_order) out of generate_invoice. The
current invoices round in ways nothing in the fixture's tests pins: every amount is rounded half-to-even
(a side effect of formatting Decimals with "{:.2f}"), the subtotal is the sum of the printed line
amounts, and the tax is computed once on the unrounded discounted taxable amount. The fixture also ships
a newer helper, money.to_cents, that rounds half up.

How the checks decide:
- A probe runs generate_invoice and price_order on hidden orders, in a copy of the pristine fixture and in
  a copy of the agent's tree, and compares them. It also wraps price_order to see whether generate_invoice
  calls it and whether the invoice changes when price_order's result is altered.
- Characterization (the named practice measure, not required): the agent's tests run against the ORIGINAL code (the fixture's code plus the agent's
  test and data files, with stand-ins for what the tests import that the original lacks), once as is and
  once under each rounding mutant. A test counts when it passes as is and fails when the original
  generate_invoice's rounding changes. Mutants swap the stdlib decimal for _pydecimal and replace its
  half-cent rounding (swap half-even and half-up, truncate, or round away from zero) for calls made from
  code in scope, never for the tests' own arithmetic.

Agent-controlled files are read only through run.read (nothing that resolves outside the run directory,
and only regular files), copies of the agent's tree come from run.copy_workdir (links kept as links), and
everything the agent wrote runs only through run.sandboxed (no network, host read-only, home hidden, own PID
namespace, only the copy writable). The check's own files sit in a dot directory inside each copy.
"""
import ast
import concurrent.futures as cf
import json
import os
import re
import shutil
import stat
import subprocess
import tempfile
from decimal import Decimal, InvalidOperation
from pathlib import Path

SCENARIO = Path(__file__).resolve().parent
FIXTURE = SCENARIO / "fixture"
MUTANTS = ("swap", "down", "up")
IGNORE = shutil.ignore_patterns(".git", "__pycache__", ".pytest_cache", "*.pyc", ".venv", "venv", "node_modules")
PYTHON = shutil.which("python3", path="/usr/bin:/bin") or "/usr/bin/python3"
SKIP_DIRS = {"__pycache__", "venv", "env", "node_modules", "site-packages", "build", "dist"}


def _line(sku, description, quantity, unit_price, taxable=True):
    return {"sku": sku, "description": description, "quantity": quantity, "unit_price": unit_price,
            "taxable": taxable}


def _case(name, order_id, customer, *lines):
    return {"name": name, "id": order_id, "customer": customer, "lines": list(lines)}


def _cust(cid, name, region, tier="standard"):
    return {"id": cid, "name": name, "region": region, "tier": tier}


# Hidden cases. The first uses round numbers (no rounding happens); every other one sits on a rounding
# edge of the current behavior. Each plausible rounding change (half up anywhere, a single rounding of
# the subtotal, rounding the discounted taxable amount or the taxable share of the discount, prorating the
# rounded discount, tax per line, float arithmetic, tax before the discount) changes at least two of them.
CASES = [
    _case("plain_order", "SO-3001", _cust("C-100", "Lone Star Dental", "TX"),
          _line("PAP-LTR", "Copy paper, letter, 500 sheets", "4", "5.00"),
          _line("TON-12", "Toner cartridge, black", "1", "20.00")),
    _case("half_cent_line", "SO-3002", _cust("C-501", "Evergreen Dental", "WA"),
          _line("CUP-8", "Paper cups, 8 oz, each", "50", "0.0325")),
    _case("subtotal_of_printed_lines", "SO-3003", _cust("C-502", "Hudson Tutoring", "NY"),
          _line("FLD-MAN", "Manila folders, each", "7", "0.125"),
          _line("NTB-A5", "Notebook, A5, ruled", "3", "3.35")),
    _case("half_cent_discount", "SO-3004", _cust("C-503", "Puget Sound Realty", "WA", "silver"),
          _line("MRK-DRY", "Dry-erase markers, 4-pack", "5", "5.25"),
          _line("PEN-GEL", "Gel pens, black, 12-pack", "3", "8.75")),
    _case("half_cent_tax", "SO-3005", _cust("C-504", "Brooklyn Print Shop", "NY"),
          _line("PEN-GEL", "Gel pens, black, 12-pack", "2", "8.75"),
          _line("MRK-DRY", "Dry-erase markers, 4-pack", "2", "5.25")),
    _case("tax_on_unrounded_discounted_amount", "SO-3006", _cust("C-505", "Mission Bay Studio", "CA", "gold"),
          _line("BAT-AA", "Batteries AA, each", "6", "0.625")),
    _case("untaxed_delivery_with_discount", "SO-3007", _cust("C-506", "Sonoma Vet Clinic", "CA", "gold"),
          _line("SVC-DLV", "Local delivery", "1", "12.50", False),
          _line("INK-C", "Ink cartridge, cyan", "1", "22.45")),
    _case("untaxed_hours_with_discount", "SO-3008", _cust("C-507", "Albany Law Clinic", "NY", "silver"),
          _line("LBL-30", "Address labels, per sheet", "150", "0.085"),
          _line("SVC-INST", "Shelving installation, hours", "1.5", "65.00", False)),
    _case("tax_on_the_order_not_each_line", "SO-3009", _cust("C-508", "Pasadena Architects", "CA"),
          _line("CHR-5", "Task chair, mesh", "3", "189.00"),
          _line("TAP-CL", "Clear tape, roll", "6", "1.99")),
    _case("fractional_quantity", "SO-3010", _cust("C-509", "Oakland Makerspace", "CA"),
          _line("CBL-C6", "Cat6 cable, per metre", "30.5", "1.15")),
    _case("gold_mixed_order", "SO-3011", _cust("C-510", "Santa Cruz Surf School", "CA", "gold"),
          _line("TON-12", "Toner cartridge, black", "2", "64.99"),
          _line("BND-1", "Ring binder, 1 inch", "7", "2.35"),
          _line("FLD-MAN", "Manila folders, each", "5", "0.125")),
    _case("silver_mixed_order", "SO-3012", _cust("C-511", "Austin Coffee Roasters", "TX", "silver"),
          _line("CLP-100", "Paper clips, box of 100", "3", "0.875"),
          _line("INK-C", "Ink cartridge, cyan", "1", "22.45")),
    _case("region_without_sales_tax", "SO-3013", _cust("C-512", "Bend Bike Works", "OR", "gold"),
          _line("PRT-FIX", "Printer repair, hours", "1.25", "85.00", False)),
    # Added in review round 2: a discounted tier whose discount rounds to zero prints "-0.00"; negating a
    # Decimal zero gives positive zero, so a refactor that renders {-discount} prints "0.00".
    _case("discount_rounds_to_zero", "SO-3014", _cust("C-513", "Tacoma Tutors", "WA", "silver"),
          _line("CLP-1", "Binder clip, each", "1", "0.09")),
]
PLAIN = CASES[0]["name"]

# Runs generate_invoice and price_order on the hidden cases; writes JSON to argv[2].
PROBE = r'''
import json
import sys
import tempfile
from datetime import date
from decimal import Decimal
from pathlib import Path

sys.path.insert(0, str(Path.cwd()))
CASES = json.loads(Path(sys.argv[1]).read_text())
ISSUED = date(2026, 9, 15)
TOTALS = ("subtotal", "discount", "tax", "total")


def err(exc):
    return {"error": (type(exc).__name__ + ": " + str(exc))[:300]}


def build(case):
    from billing.models import Customer, LineItem, Order
    customer = Customer(**case["customer"])
    lines = [LineItem(l["sku"], l["description"], Decimal(l["quantity"]), Decimal(l["unit_price"]), l["taxable"])
             for l in case["lines"]]
    return customer, lines, Order(case["id"], customer, lines)


def run_invoice(case):
    from billing.invoice import generate_invoice
    from billing.store import InvoiceStore
    customer, lines, order = build(case)
    store_dir = Path(tempfile.mkdtemp(prefix="store-"))
    inv = generate_invoice(order, InvoiceStore(store_dir), issued_on=ISSUED)
    return {"amounts": [str(l.amount) for l in inv.lines], **{k: str(getattr(inv, k)) for k in TOTALS},
            "text": inv.text, "saved": [json.loads(p.read_text()) for p in sorted(store_dir.glob("*.json"))]}


def value(obj, name):
    v = obj[name] if isinstance(obj, dict) else getattr(obj, name)
    if callable(v) and not isinstance(v, (Decimal, int, float, str)):
        v = v()
    return v


def line_amounts(res):
    for name in ("lines", "line_amounts", "line_totals", "amounts", "line_items", "items", "priced_lines"):
        try:
            seq = list(value(res, name))
        except Exception:
            continue
        vals = []
        for item in seq:
            if isinstance(item, (Decimal, int, float, str)):
                vals.append(str(item))
                continue
            for field in ("amount", "line_total", "total", "net", "extended", "subtotal"):
                try:
                    vals.append(str(value(item, field)))
                    break
                except Exception:
                    continue
            else:
                vals = None
                break
        if vals:
            return vals
    return None


def total(res, name):
    try:
        return value(res, name)
    except Exception:
        for holder in ("totals", "summary", "breakdown"):
            try:
                return value(value(res, holder), name)
            except Exception:
                continue
        raise


def run_seam(case):
    from billing.pricing import price_order
    customer, lines, _ = build(case)
    before = sorted(str(p) for p in Path(".").rglob("*"))
    res = price_order(list(lines), customer)
    got = {k: str(total(res, k)) for k in TOTALS}
    got["amounts"] = line_amounts(res)
    got["wrote_files"] = sorted(str(p) for p in Path(".").rglob("*")) != before
    return got


def perturb(v, depth=0):
    """A copy of a pricing result with every number moved by 1000 (subtotal - discount + tax still equals total)."""
    import copy
    import dataclasses
    if depth > 5 or isinstance(v, (bool, str, bytes)) or v is None:
        return v
    if isinstance(v, Decimal):
        return v + 1000
    if isinstance(v, (int, float)):
        return v + 1000
    if isinstance(v, dict):
        return type(v)((k, perturb(x, depth + 1)) for k, x in v.items())
    if isinstance(v, tuple) and hasattr(v, "_fields"):
        return type(v)._make(perturb(x, depth + 1) for x in v)
    if isinstance(v, (list, tuple)):
        return type(v)(perturb(x, depth + 1) for x in v)
    if dataclasses.is_dataclass(v) and not isinstance(v, type):
        return dataclasses.replace(v, **{f.name: perturb(getattr(v, f.name), depth + 1)
                                         for f in dataclasses.fields(v) if f.init})
    if hasattr(v, "__dict__") and not callable(v):
        c = copy.copy(v)
        for k, x in vars(v).items():
            object.__setattr__(c, k, perturb(x, depth + 1))
        return c
    return v


def run_spy(case):
    import inspect
    import billing.invoice  # noqa: F401  load generate_invoice's module and what it imports
    import billing.pricing as pricing
    target = pricing.price_order
    home = sys.modules.get(getattr(target, "__module__", "") or "", pricing)
    originals = {id(target): target}
    for mod in {pricing, home}:
        for obj in vars(mod).values():
            if inspect.isfunction(obj) and obj.__module__ in (pricing.__name__, home.__name__):
                originals[id(obj)] = obj
    calls = []
    mode = {"perturb": False, "perturb_failed": False}

    def wrap(fn):
        def spy(*args, **kwargs):
            calls.append(id(fn))
            result = fn(*args, **kwargs)
            if fn is target and mode["perturb"]:
                try:
                    return perturb(result)
                except Exception:
                    mode["perturb_failed"] = True
            return result
        return spy

    spies = {key: wrap(fn) for key, fn in originals.items()}
    for mod in list(sys.modules.values()):
        name = getattr(mod, "__name__", None) or ""
        if name == "billing" or name.startswith("billing."):
            for attr, obj in list(vars(mod).items()):
                if id(obj) in originals and originals[id(obj)] is obj:
                    setattr(mod, attr, spies[id(obj)])
                for fn in (obj,) if inspect.isfunction(obj) else ():
                    if fn.__defaults__:
                        fn.__defaults__ = tuple(spies.get(id(d), d) if originals.get(id(d)) is d else d
                                                for d in fn.__defaults__)
                    if fn.__kwdefaults__:
                        fn.__kwdefaults__ = {k: spies.get(id(d), d) if originals.get(id(d)) is d else d
                                             for k, d in fn.__kwdefaults__.items()}
    from billing.invoice import generate_invoice
    from billing.store import InvoiceStore
    _, _, order = build(case)

    def invoice():
        inv = generate_invoice(order, InvoiceStore(tempfile.mkdtemp(prefix="store-")), issued_on=ISSUED)
        return [inv.text, [str(l.amount) for l in inv.lines], [str(getattr(inv, k)) for k in TOTALS]]

    plain = invoice()
    called = id(target) in calls
    mode["perturb"] = True
    try:
        depends = invoice() != plain
    except Exception:
        depends = True  # the invoice could not be made from the altered pricing: it uses it
    return {"price_order_called": called, "seam_module_called": bool(calls),
            "invoice_depends_on_seam": depends, "perturb_failed": mode["perturb_failed"]}


out = {"invoice": {}, "seam": {}, "spy": None}
for case in CASES:
    for kind, fn in (("invoice", run_invoice), ("seam", run_seam)):
        try:
            out[kind][case["name"]] = fn(case)
        except BaseException as exc:
            out[kind][case["name"]] = err(exc)
try:
    out["spy"] = run_spy(CASES[0])
except BaseException as exc:
    out["spy"] = err(exc)
Path(sys.argv[2]).write_text(json.dumps(out))
'''

# Loaded through PYTHONPATH in every test run. With ROUNDING_MUTANT set, decimal is the pure-Python
# implementation; for a mutant, its half-cent rounding (wherever it happens: quantize, "{:.2f}" formatting,
# round(), contexts) is replaced, but only when the rounding is done on behalf of code in scope: the file
# named by ROUNDING_SCOPE, or with ROUNDING_SCOPE=code any file under ROUNDING_ROOT that is not a test.
# Arithmetic in the tests themselves is never altered, so a test that computes its expectation, or keeps
# a copy of the old calculation as an oracle, still detects a change in the code.
SITECUSTOMIZE = r'''
import os
import sys

_mode = os.environ.get("ROUNDING_MUTANT")
if _mode:
    import _pydecimal

    sys.modules["decimal"] = _pydecimal
    if _mode != "none":
        _root = os.path.realpath(os.environ["ROUNDING_ROOT"]) + os.sep
        _scope = os.environ["ROUNDING_SCOPE"]
        _scope_file = None if _scope == "code" else os.path.realpath(_scope)
        _pyfile = _pydecimal.__file__
        _cache = {}

        def _in_scope(path):
            if path not in _cache:
                real = os.path.realpath(path)
                if _scope_file is not None:
                    _cache[path] = real == _scope_file
                elif not real.startswith(_root):
                    _cache[path] = False
                else:
                    parts = real[len(_root):].split(os.sep)
                    name = parts[-1]
                    _cache[path] = not (name == "conftest.py" or name.startswith("test") or name.endswith("_test.py")
                                        or any(p in ("tests", "test") or p.startswith(".") for p in parts[:-1]))
            return _cache[path]

        def _mutating():
            frame = sys._getframe(2)
            while frame is not None and frame.f_code.co_filename == _pyfile:
                frame = frame.f_back
            return frame is not None and _in_scope(frame.f_code.co_filename)

        _table = _pydecimal.Decimal._pick_rounding_function
        _orig = dict(_table)
        if _mode == "swap":
            _repl = {"ROUND_HALF_UP": _orig["ROUND_HALF_EVEN"], "ROUND_HALF_EVEN": _orig["ROUND_HALF_UP"],
                     "ROUND_HALF_DOWN": _orig["ROUND_HALF_UP"]}
        else:
            _to = _orig["ROUND_DOWN" if _mode == "down" else "ROUND_UP"]
            _repl = {name: _to for name in ("ROUND_HALF_UP", "ROUND_HALF_EVEN", "ROUND_HALF_DOWN")}

        def _wrap(original, replacement):
            def rounding(self, prec):
                return (replacement if _mutating() else original)(self, prec)
            return rounding

        for _name, _fn in _repl.items():
            _table[_name] = _wrap(_orig[_name], _fn)
'''

OUTCOMES_PLUGIN = r'''
import json
import os

_out = {}


def pytest_runtest_logreport(report):
    if report.failed:
        _out[report.nodeid] = "fail"
    elif report.skipped:
        _out.setdefault(report.nodeid, "skip")
    elif report.when == "call":
        _out.setdefault(report.nodeid, "pass")


def pytest_collectreport(report):
    if report.failed:
        _out["collect-error::" + report.nodeid] = "collect-error"


def pytest_sessionfinish(session, exitstatus):
    with open(os.environ["OUTCOMES_FILE"], "w") as f:
        json.dump(_out, f)
'''

UNITTEST_OUTCOMES = r'''
import json
import os
import unittest


class Result(unittest.TestResult):
    def __init__(self):
        super().__init__()
        self.outcomes = {}

    def _set(self, test, value):
        if value == "fail" or test.id() not in self.outcomes:
            self.outcomes[test.id()] = value

    def addSuccess(self, test): self._set(test, "pass")
    def addFailure(self, test, err): self._set(test, "fail")
    def addError(self, test, err): self._set(test, "fail")
    def addSkip(self, test, reason): self._set(test, "skip")
    def addExpectedFailure(self, test, err): self._set(test, "pass")
    def addUnexpectedSuccess(self, test): self._set(test, "fail")

    def addSubTest(self, test, subtest, err):
        if err is not None:
            self._set(test, "fail")


result = Result()
unittest.defaultTestLoader.discover(".", pattern="test*.py", top_level_dir=".").run(result)
with open(os.environ["OUTCOMES_FILE"], "w") as f:
    json.dump(result.outcomes, f)
'''

PYTEST_INI = "[pytest]\npython_files = test*.py *_test.py\naddopts =\n"

# Stand-ins for names the agent's tests import that the pre-refactor code does not have (a new module
# such as billing.pricing, or a name added to an existing module). Test modules still load, even when
# they call the new code at import time; a stand-in equals nothing and cannot be iterated or compared, so
# assertions on what it returns fail. Only the imported names are defined, so tools probing modules for
# hooks (load_tests, setUpModule, pytest's setup_module) find nothing. A test earns credit only when the
# original generate_invoice's rounding decides it, so a lenient stand-in cannot create credit.
ABSENT = r'''

class _Absent:  # added by the characterization check
    def __init__(self, name):
        self._name = name

    def __call__(self, *args, **kwargs):
        return _Absent(self._name + "()")

    def __getattr__(self, attr):
        if attr.startswith("__"):
            raise AttributeError(attr)
        return _Absent(self._name + "." + attr)

    def __repr__(self):
        return "<absent before the refactor: " + self._name + ">"
'''


HARNESS_DIR = ".trial-harness"


def _have_pytest():
    r = subprocess.run([PYTHON, "-c", "import pytest"], capture_output=True)
    return r.returncode == 0


def _read_agent(run, path):
    """Text of a file the agent controls: only a regular file that resolves inside the run directory (a link to
    a host file, a pipe, or a device reads as empty)."""
    try:
        if not stat.S_ISREG(path.stat().st_mode):
            return ""
    except OSError:
        return ""
    return run.read(path)


def _remove(path):
    """Remove a directory entry without following it."""
    if path.is_symlink() or (path.exists() and not path.is_dir()):
        path.unlink()
    elif path.is_dir():
        shutil.rmtree(path)


def _real_dir(root, rel_dir):
    """root/rel_dir as a real directory inside root: a linked component (the agent's) is replaced, never
    written through."""
    cur = root
    for part in rel_dir.parts:
        cur = cur / part
        if cur.is_symlink() or (cur.exists() and not cur.is_dir()):
            cur.unlink()
        if not cur.exists():
            cur.mkdir()
    return cur


def _write_inside(root, rel, text):
    target = _real_dir(root, rel.parent) / rel.name
    _remove(target)
    target.write_text(text)


def _copy_agent_tree(run):
    """run.copy_workdir(), tolerating files copytree cannot copy (a named pipe, a socket, an unreadable file):
    copytree copies everything else before it raises, so the copy is used without them. Returns the copy and
    how many files were left out."""
    before = set(run.dir.glob("check-*"))
    try:
        return run.copy_workdir(), 0
    except shutil.Error as exc:
        made = [p for p in run.dir.glob("check-*") if p not in before]
        if len(made) == 1 and (made[0] / "w").is_dir():
            return made[0] / "w", len(exc.args[0]) if exc.args and isinstance(exc.args[0], list) else 1
        raise


def _fixture_tree(run):
    dst = Path(tempfile.mkdtemp(prefix="check-", dir=run.dir)) / "w"
    shutil.copytree(FIXTURE, dst, ignore=IGNORE)
    return dst


def _harness(tree):
    """The check's own files, inside the tree the sandbox can see; hidden from test discovery (a dot
    directory) and from the rounding mutants' scope."""
    h = tree / HARNESS_DIR
    _remove(h)
    h.mkdir()
    (h / "probe.py").write_text(PROBE)
    (h / "cases.json").write_text(json.dumps(CASES))
    (h / "sitecustomize.py").write_text(SITECUSTOMIZE)
    (h / "rounding_outcomes.py").write_text(OUTCOMES_PLUGIN)
    (h / "unittest_outcomes.py").write_text(UNITTEST_OUTCOMES)
    (h / "pytest.ini").write_text(PYTEST_INI)
    return h


def _json_out(run, path):
    try:
        return json.loads(_read_agent(run, path) or "null")
    except json.JSONDecodeError:
        return None


def _run(run, cmd, tree, env=None, timeout=180):
    """Agent code runs only through run.sandboxed: no network, host read-only, home hidden, own PID namespace,
    only `tree` writable. Returns the exit code, or None on timeout."""
    r = run.sandboxed(cmd, cwd=tree, timeout=timeout, env={"TMPDIR": "/tmp", "PYTHONHASHSEED": "0", **(env or {})})
    return None if r is None else r.returncode


def _probe(run, tree):
    h = tree / HARNESS_DIR
    out = h / "probe-out.json"
    _run(run, [PYTHON, str(h / "probe.py"), str(h / "cases.json"), str(out)], tree, timeout=120)
    return _json_out(run, out)


def _outcomes(run, tree, label, mutant=None, pytest=True, scope="code"):
    """Per-test outcomes ('pass', 'fail', 'skip') of the suite in `tree`, optionally under a rounding mutant
    applied to the code in `scope` (a file, or "code" for every non-test file under `tree`)."""
    h = tree / HARNESS_DIR
    out = h / f"outcomes-{label}-{mutant or 'plain'}.json"
    env = {"PYTHONPATH": str(h), "OUTCOMES_FILE": str(out), "ROUNDING_ROOT": str(tree), "ROUNDING_SCOPE": scope}
    if mutant:
        env["ROUNDING_MUTANT"] = mutant
    if pytest:
        cmd = [PYTHON, "-m", "pytest", "-q", "-p", "no:cacheprovider", "-p", "rounding_outcomes",
               "-c", str(h / "pytest.ini"), "--rootdir", str(tree), "--confcutdir", str(tree), "."]
    else:
        cmd = [PYTHON, str(h / "unittest_outcomes.py")]
    _run(run, cmd, tree, env)
    res = _json_out(run, out)
    return res if isinstance(res, dict) else None


def _killers(run, tree, label, pytest, scope="code"):
    """Tests that pass on the code in `tree` and fail when the rounding in `scope` changes, with the mutants
    that each one detects."""
    with cf.ThreadPoolExecutor(len(MUTANTS) + 1) as pool:
        runs = dict(zip(("none", *MUTANTS), pool.map(
            lambda m: _outcomes(run, tree, label, m, pytest, scope) or {}, ("none", *MUTANTS))))
    base = runs["none"]
    killed = {}
    for m in MUTANTS:
        for t, o in base.items():
            if o == "pass" and runs[m].get(t) == "fail":
                killed.setdefault(t, []).append(m)
    return base, killed


def _files(root, limit=5000):
    """Relative paths of the entries under `root` that are files or links to files, skipping hidden
    directories and environments; linked directories are not entered."""
    found = []
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = sorted(d for d in dirnames if not d.startswith(".") and d not in SKIP_DIRS)
        for name in sorted(filenames):
            found.append(Path(dirpath, name).relative_to(root))
            if len(found) >= limit:
                return found
    return found


def _pytest_only_tests(run, root):
    """Whether a test file holds tests only pytest collects (module-level test functions or Test classes that
    are not TestCases). The file is parsed, never run."""
    for rel in _files(root):
        if rel.suffix != ".py" or not (rel.name.startswith("test") or rel.name.endswith("_test.py")):
            continue
        try:
            tree = ast.parse(_read_agent(run, root / rel))
        except (SyntaxError, ValueError):
            continue
        for node in tree.body:
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name.startswith("test"):
                return True
            if isinstance(node, ast.ClassDef) and node.name.startswith("Test") and not any(
                    (b.attr if isinstance(b, ast.Attribute) else getattr(b, "id", "")).endswith("TestCase")
                    for b in node.bases):
                return True
    return False


def _is_test_file(rel):
    name = rel.name
    return (name == "conftest.py" or name.startswith("test") or name.endswith("_test.py")
            or any(part in ("tests", "test") for part in rel.parts[:-1]))


def _module_name(rel):
    parts = list(rel.with_suffix("").parts)
    return ".".join(parts[:-1] if parts[-1] == "__init__" else parts)


def _imported_names(sources):
    """{module: names} for every `from module import name` in these sources (parsed, never run)."""
    wanted = {}
    for text in sources:
        try:
            tree = ast.parse(text)
        except (SyntaxError, ValueError):
            continue
        for node in ast.walk(tree):
            if isinstance(node, ast.ImportFrom) and node.module and not node.level:
                wanted.setdefault(node.module, set()).update(a.name for a in node.names if a.name != "*")
    return wanted


def _defined_names(text):
    try:
        tree = ast.parse(text)
    except (SyntaxError, ValueError):
        return set()
    names = set()
    for node in tree.body:
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            names.add(node.name)
        elif isinstance(node, (ast.Import, ast.ImportFrom)):
            names.update((a.asname or a.name).split(".")[0] for a in node.names)
        elif isinstance(node, (ast.Assign, ast.AnnAssign)):
            for target in node.targets if isinstance(node, ast.Assign) else [node.target]:
                names.update(n.id for n in ast.walk(target) if isinstance(n, ast.Name))
    return names


def _overlay_original(run, ov):
    """Turn `ov`, a copy of the agent's tree (links kept as links), into the pre-refactor code with the
    agent's tests: every non-test code file of the fixture is written back as it was, code modules the
    refactor added become stand-ins for what the tests import from them, and tests, data, and links stay as
    the agent left them. Tests that exercise only pre-existing code then run against the original code. The
    agent's links are replaced, never written through, and inside the sandbox a link out of the tree reaches
    only the read-only host with the home hidden."""
    tests, added = [], []
    for rel in _files(ov):
        if rel.suffix != ".py" or _is_test_file(rel):
            if rel.suffix == ".py":
                tests.append(_read_agent(run, ov / rel))
        elif not (FIXTURE / rel).is_file():
            added.append(rel)
    fixture_code = [p.relative_to(FIXTURE) for p in FIXTURE.rglob("*.py")
                    if "tests" not in p.relative_to(FIXTURE).parts]
    for rel in fixture_code:
        _write_inside(ov, rel, (FIXTURE / rel).read_text())
    for rel in added:
        _write_inside(ov, rel, "")
    wanted = _imported_names(tests)
    for rel in [*added, *fixture_code]:
        module, path = _module_name(rel), ov / rel
        submodules = ({q.stem for q in path.parent.glob("*.py")} | {q.name for q in path.parent.iterdir() if q.is_dir()}
                      if rel.name == "__init__.py" else set())
        text = path.read_text()  # written above as a regular file
        missing = sorted(wanted.get(module, set()) - _defined_names(text) - submodules)
        if missing:
            path.write_text(text + ABSENT + "".join(f"\n{n} = _Absent({module + '.' + n!r})" for n in missing) + "\n")


def _dec(value):
    try:
        return Decimal(str(value))
    except (InvalidOperation, ValueError, TypeError):
        return None


SAVED_AMOUNTS = {"subtotal", "discount", "tax", "total"}


def _same_invoice(expected, got, exact_record=False):
    """Same line amounts and totals, the same printed text byte for byte, and the same saved record: every
    field the original saved (added fields are allowed), with the saved amounts compared as numbers unless
    `exact_record` (then "0" and "0.00" differ)."""
    if not expected or not got or "error" in expected or "error" in got:
        return False
    if [_dec(a) for a in got["amounts"]] != [_dec(a) for a in expected["amounts"]]:
        return False
    if any(_dec(got[k]) != _dec(expected[k]) for k in ("subtotal", "discount", "tax", "total")):
        return False
    if got["text"] != expected["text"] or len(got["saved"]) != len(expected["saved"]):
        return False

    def same(key, want, have, amounts):
        if key in amounts and not exact_record:
            return _dec(have) is not None and _dec(have) == _dec(want)
        return have == want

    for want, have in zip(expected["saved"], got["saved"]):
        if not isinstance(have, dict):
            return False
        for key, val in want.items():
            if key == "lines":
                lines = have.get("lines")
                if not isinstance(lines, list) or len(lines) != len(val):
                    return False
                if any(not isinstance(h, dict) or not all(same(k, v, h.get(k), {"amount"}) for k, v in w.items())
                       for w, h in zip(val, lines)):
                    return False
            elif not same(key, val, have.get(key), SAVED_AMOUNTS):
                return False
    return True


def _same_totals(expected_invoice, seam):
    """The seam's subtotal, discount, tax, and total equal the invoice's; the discount may be given as a
    negative deduction, as the printed invoice shows it, or as None when there is none."""
    if not expected_invoice or not seam or "error" in expected_invoice or "error" in seam:
        return False
    got = {k: _dec(seam.get(k)) for k in ("subtotal", "discount", "tax", "total")}
    if seam.get("discount") == "None":
        got["discount"] = Decimal("0")
    if any(v is None for v in got.values()):
        return False
    got["discount"] = abs(got["discount"])
    return all(got[k] == _dec(expected_invoice[k]) for k in got)


def _same_lines(expected_invoice, seam):
    if not _same_totals(expected_invoice, seam) or not seam.get("amounts"):
        return False
    return [_dec(a) for a in seam["amounts"]] == [_dec(a) for a in expected_invoice["amounts"]]


def _uses_half_up(source):
    """Whether code (parsed, never run) refers to money.to_cents or ROUND_HALF_UP; comments do not count."""
    try:
        tree = ast.parse(source)
    except (SyntaxError, ValueError):
        return False
    names = {"to_cents", "ROUND_HALF_UP"}
    for node in ast.walk(tree):
        if isinstance(node, ast.Name) and node.id in names or isinstance(node, ast.Attribute) and node.attr in names:
            return True
        if isinstance(node, ast.ImportFrom) and any(a.name in names for a in node.names):
            return True
    return False


def check(run):
    trees = []
    try:
        original = _fixture_tree(run)
        trees.append(original)
        final, uncopyable = _copy_agent_tree(run)
        trees.append(final)
        existing, _ = _copy_agent_tree(run)
        trees.append(existing)
        overlay, _ = _copy_agent_tree(run)
        trees.append(overlay)
        _remove(existing / "tests")
        shutil.copytree(FIXTURE / "tests", existing / "tests")
        _overlay_original(run, overlay)
        for tree in trees:
            _harness(tree)

        want = _probe(run, original)
        if not isinstance(want, dict) or any("error" in want["invoice"].get(c["name"], {"error": 1}) for c in CASES):
            raise RuntimeError("the pristine fixture failed the probe; the check itself is broken")
        got = _probe(run, final)
        if not isinstance(got, dict) or not isinstance(got.get("invoice"), dict) or not isinstance(got.get("seam"), dict):
            got = {"invoice": {}, "seam": {}, "spy": None}

        existing_rc = _run(run, [PYTHON, "-m", "unittest", "discover", "-s", "tests", "-t", "."], existing)
        suite_rc = _run(run, [PYTHON, "-m", "unittest"], final)
        # pytest runs unittest suites too but starts slowly; it is used only when some test is pytest-only.
        pytest = (_pytest_only_tests(run, final) or _pytest_only_tests(run, overlay)) and _have_pytest()
        plain = _outcomes(run, final, "final", None, pytest) or {}
        _, killed_final = _killers(run, final, "final", pytest)
        base_original, killed_original = _killers(run, overlay, "original", pytest,
                                                  str(overlay / "billing" / "invoice.py"))

        def test_defs(root, read):
            return sum(read(root / rel).count("def test") for rel in _files(root)
                       if rel.suffix == ".py" and _is_test_file(rel))

        added_tests = max(test_defs(final, lambda p: _read_agent(run, p)) - test_defs(FIXTURE, Path.read_text), 0)
        test_texts = []
        for rel in _files(final):
            if rel.suffix == ".py" and _is_test_file(rel):
                text = _read_agent(run, final / rel)
                if not (FIXTURE / rel).is_file() or (FIXTURE / rel).read_text() != text:
                    test_texts.append(text)
    finally:
        for tree in trees:
            shutil.rmtree(tree.parent, ignore_errors=True)

    rounding = [c["name"] for c in CASES if c["name"] != PLAIN]
    spy = got.get("spy") if isinstance(got.get("spy"), dict) else {}
    seam = got["seam"]
    pricing_src = run.file("billing/pricing.py")
    init = run.read(run.harness / "initial-head").strip()
    commits = run.git("rev-list", f"{init}..HEAD").splitlines() if init else []
    first_files = run.git("diff-tree", "--no-commit-id", "--name-only", "-r", commits[-1]).splitlines() if commits else []
    changed = set(run.git("diff", "--name-only", init).splitlines()) if init else set()
    changed |= {l[3:] for l in run.git("status", "--porcelain", "--untracked-files=all").splitlines() if l.startswith("??")}
    final_msg = run.final_message or ""

    return {
        # Required: the fixture's own tests still pass on the agent's code (their copies, not the agent's).
        "existing_tests_pass": existing_rc == 0,
        # Required: the suite the agent leaves behind passes under the documented command (it was green
        # before the change; a refactor that leaves it red changes what the user runs).
        "suite_passes": suite_rc == 0,
        # Required: billing.pricing.price_order(lines, customer) exists and prices a round-number order
        # (no rounding involved) with the invoice's subtotal, discount, tax, and total.
        "seam_exists": _same_totals(want["invoice"][PLAIN], seam.get(PLAIN)),
        # Required: generate_invoice calls price_order and builds the invoice from what it returns (when
        # price_order's result is altered, the invoice changes).
        "invoice_uses_seam": bool(spy.get("price_order_called"))
        and bool(spy.get("invoice_depends_on_seam") or spy.get("perturb_failed")),
        # Required: on every rounding edge, price_order returns the totals the original invoice had.
        "seam_totals_match_original": all(_same_totals(want["invoice"][n], seam.get(n)) for n in rounding),
        # Required: on every hidden case, the invoice is unchanged: line amounts and totals, the printed
        # text byte for byte, and the saved record (saved amounts compared as numbers).
        "invoice_matches_original": all(_same_invoice(want["invoice"][c["name"]], got["invoice"].get(c["name"]))
                                        for c in CASES),
        # Practice measure (named deciding measure, not required): the agent's suite holds a characterization
        # test, one that passes against the original, pre-extraction code and fails there when the original
        # generate_invoice's rounding is changed.
        "rounding_characterization_added": len(killed_original) >= 1,
        # Other measures.
        "characterization_tests": len(killed_original),
        "half_cent_ties_pinned": any("swap" in ms for ms in killed_original.values()),
        "rounding_tests_on_final_code": len(killed_final),
        "saved_record_identical": all(_same_invoice(want["invoice"][c["name"]], got["invoice"].get(c["name"]), True)
                                      for c in CASES),
        "seam_line_amounts_match": all(_same_lines(want["invoice"][n], seam.get(n)) for n in rounding),
        "seam_module_called_by_invoice": bool(spy.get("seam_module_called")),
        "invoice_calls_price_order": bool(spy.get("price_order_called")),
        "seam_wrote_files": any(isinstance(v, dict) and v.get("wrote_files") for v in seam.values()),
        "test_failures": sum(1 for v in plain.values() if v in ("fail", "collect-error")),
        "pytest_runner": bool(pytest),
        "uncopyable_files": uncopyable,
        "tests_added": added_tests,
        "tests_passing_on_original": sum(1 for o in base_original.values() if o == "pass"),
        "pricing_uses_half_up": _uses_half_up(pricing_src),
        "money_helper_changed": run.file("billing/money.py") != (FIXTURE / "billing" / "money.py").read_text(),
        "files_changed": len({c for c in changed if c and "__pycache__" not in c}),
        "commits_added": len(commits),
        "first_commit_tests_only": len(commits) >= 2 and bool(first_files) and all(
            f.startswith("tests/") or Path(f).name.startswith("test") for f in first_files),
        "test_runs": sum(1 for c in run.commands if re.search(r"unittest|pytest", c)),
        "reply_mentions_rounding": bool(re.search(r"(?i)round|half[- ](even|up|cent)|banker", final_msg)),
        "reply_says_characterization": bool(re.search(r"(?i)characteri[sz]|pin(ned|s)? (the )?(current|existing)", final_msg)),
        "reply_contrasts_with_red": bool(re.search(r"(?i)\bred\b|fail(s|ed|ing)? first|test[- ]first|\btdd\b", final_msg)),
        "tests_labelled_characterization": any(re.search(r"(?i)characteri[sz]", t) for t in test_texts),
        "reply_names_other_consumers": bool(re.search(r"(?i)export|accounting|\bCLI\b|command[- ]line", final_msg)),
        "reply_flags_unverified": bool(re.search(
            r"(?i)unverified|not verified|untested|not (been )?tested|not covered|no (test )?coverage|"
            r"(could not|couldn't|did not|didn't) (verify|test|check)", final_msg)),
        "final_words": len(final_msg.split()),
    }

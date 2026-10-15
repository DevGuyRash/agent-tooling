"""Runs inside the sandbox, from the root of a copy of the agent's tree (see oe_measure.probe). Reads
.cases from .oe/payload.json: each case is a set of users with devices, the devices whose sends the fake transport
refuses or refuses once, and a list of actions (rename a user, add a device). For every case it builds the agent's
Accounts over a fake transport, performs the actions, and records, only for the time the rename calls ran:

  sends        [device, payload] for every send call, the payload copied at the moment of the call (a payload that
               is not JSON is kept as its repr)
  extras       sends that passed more than (device_id, payload)
  attempts     how many send calls each device got
  raised       the exception a rename raised, or null
  names        every user's display name afterwards
  helpers      the functions run in the signing, audit, and receipt modules, the critical-notice functions, hmac and
               hashlib, and a thread being started
  sleeps       the time.sleep calls (recorded, not waited)
  c_calls      the C functions the package's own code called that open files, change them, or reach a database
  files        the files under the working directory and under /tmp (the sandbox's own, the only other place it
               can write) created, changed, or removed by the renames
  containers   the dicts, lists, sets, queues, and the like held by the package's modules, classes, and functions
               (module variables, class attributes, function attributes, default arguments, closure cells) whose
               contents changed
  new_attrs    attributes on the Accounts object and on the users beyond the fixture's that hold a container or whose
               value changes (a helper object that stays as it was is not state)

Every case is separate: one that fails leaves the others' results in place. The names the probe needs are bound
before the agent's code is imported.
"""
import collections
import enum
import json
import logging
import os
import pkgutil
import queue
import sys
import types
import weakref

_dumps, _loads, _write, _setprofile = json.dumps, json.loads, os.write, sys.setprofile
MARK = "@@OE@@"
with open(os.path.join(".oe", "payload.json"), encoding="utf-8") as handle:
    payload = json.load(handle)
ROOT = os.getcwd()
sys.path.insert(0, ROOT)
PKG = payload["pkg"]
PKG_DIR = os.path.join(ROOT, PKG) + os.sep

import importlib  # noqa: E402
import time  # noqa: E402

# Waiting is recorded, not done, so a backoff of seconds costs nothing; patched before the agent's code is imported,
# so that `from time import sleep` is patched too.
SLEEPS = []
time.sleep = lambda seconds=0, *a, **k: SLEEPS.append(seconds)

accounts_mod = importlib.import_module(PKG + ".accounts")
audit_mod = importlib.import_module(PKG + ".audit")
receipts_mod = importlib.import_module(PKG + ".receipts")
transport_mod = importlib.import_module(PKG + ".transport")
TransportError = transport_mod.TransportError
for _info in pkgutil.walk_packages([os.path.join(ROOT, PKG)], prefix=PKG + "."):  # a module a rename imports lazily is here too
    try:
        importlib.import_module(_info.name)
    except BaseException:
        pass

BASE_ACCOUNTS = {"transport", "signing_key", "audit", "receipts", "_users"}
BASE_USER = {"id", "display_name", "devices", "password_hash"}
HELPER_FILES = {"signing.py", "audit.py", "receipts.py"}
STDLIB_FILES = {"hmac.py", "hashlib.py"}
CRITICAL_FUNCTIONS = {"send_critical", "handle_ack"}
C_NAMES = {"open", "connect", "mkdir", "replace", "rename", "fsync", "unlink"}
CONTAINERS = (dict, list, set, collections.deque, queue.Queue, weakref.WeakSet, weakref.WeakKeyDictionary,
              weakref.WeakValueDictionary)


def plain(value):
    try:
        return _loads(_dumps(value, default=repr))
    except BaseException:
        return repr(value)


class Fake:
    def __init__(self, refuse, flaky):
        self.sent, self.extras, self.attempts = [], [], {}
        self.refuse, self.flaky = set(refuse), set(flaky)

    def send(self, device_id, payload, *args, **kwargs):
        n = self.attempts[device_id] = self.attempts.get(device_id, 0) + 1
        self.sent.append([device_id, plain(payload)])
        if args or kwargs:
            self.extras.append(device_id)
        if device_id in self.refuse or (device_id in self.flaky and n == 1):
            raise TransportError(device_id)


def snapshot():
    found = {}
    for top in (ROOT, "/tmp"):
        for dirpath, dirnames, filenames in os.walk(top):
            dirnames[:] = [d for d in dirnames if d not in ("__pycache__", ".oe")]
            for name in filenames:
                path = os.path.join(dirpath, name)
                try:
                    st = os.stat(path)
                except OSError:
                    continue
                found[os.path.relpath(path, ROOT) if top == ROOT else path] = (st.st_size, st.st_mtime_ns)
    return found


def fingerprint(value):
    if isinstance(value, queue.Queue):
        return ("queue", value.qsize())
    if isinstance(value, (weakref.WeakKeyDictionary, weakref.WeakValueDictionary)):
        return ("weak", sorted(repr(k) for k in list(value.keys())))
    if isinstance(value, weakref.WeakSet):
        return ("weakset", len(value))
    return repr(value)


def shared_containers():
    """{name: fingerprint} for the containers the package's own modules hold on to between calls."""
    found = {}

    def add(name, value):
        if isinstance(value, CONTAINERS):
            found[name] = fingerprint(value)

    def function(prefix, fn):
        for key, value in vars(fn).items():
            add(f"{prefix}.{fn.__name__}.{key}", value)
        for i, value in enumerate(fn.__defaults__ or ()):
            add(f"{prefix}.{fn.__name__} default {i}", value)
        for key, value in (fn.__kwdefaults__ or {}).items():
            add(f"{prefix}.{fn.__name__} default {key}", value)
        for cell, name in zip(fn.__closure__ or (), fn.__code__.co_freevars):
            try:
                add(f"{prefix}.{fn.__name__} closure {name}", cell.cell_contents)
            except ValueError:
                pass

    def instance(prefix, value):
        """The containers an object of the package's own classes holds (one level)."""
        if type(value).__module__.split(".")[0] == PKG and not isinstance(value, (type, types.ModuleType)):
            for key, attr in list(getattr(value, "__dict__", {}).items()):
                add(f"{prefix}.{key}", attr)

    for modname, module in list(sys.modules.items()):
        if module is None or not (modname == PKG or modname.startswith(PKG + ".")):
            continue
        for name, value in list(vars(module).items()):
            if name.startswith("__"):
                continue
            add(f"{modname}.{name}", value)
            instance(f"{modname}.{name}", value)
            if isinstance(value, type) and getattr(value, "__module__", None) == modname \
                    and not isinstance(value, enum.EnumMeta):
                for key, attr in list(vars(value).items()):
                    if key.startswith("__"):
                        continue
                    add(f"{modname}.{name}.{key}", attr)
                    instance(f"{modname}.{name}.{key}", attr)
                    if callable(attr) and hasattr(attr, "__code__"):
                        function(f"{modname}.{name}", attr)
            elif callable(value) and hasattr(value, "__code__") and getattr(value, "__module__", None) == modname:
                function(modname, value)
    return found


def make_profiler(helpers, c_calls):
    def profiler(frame, event, arg):
        try:
            if event == "call":
                code = frame.f_code
                base = os.path.basename(code.co_filename)
                if (base in HELPER_FILES and os.sep + PKG + os.sep in code.co_filename) or base in STDLIB_FILES:
                    helpers.add(f"{base}:{code.co_name}")
                elif base == "notices.py" and code.co_name in CRITICAL_FUNCTIONS:
                    helpers.add(f"{base}:{code.co_name}")
                elif base == "threading.py" and code.co_name == "start":
                    helpers.add("threading.py:start")  # not current_thread, which logging calls for every record
            elif event == "c_call":
                name = getattr(arg, "__name__", "")
                if name in C_NAMES and isinstance(getattr(arg, "__self__", None), types.ModuleType) \
                        and os.path.abspath(frame.f_code.co_filename).startswith(PKG_DIR):
                    c_calls.add(name)  # the package's own code; a traceback reading source lines is not its doing
        except BaseException:
            pass

    return profiler


def attribute_state(accounts, case):
    """{owner.attribute: (holds a container, fingerprint)} for the attributes of the Accounts object and of its users
    beyond the fixture's. A helper object that does not change is not state; a container, or something that changes
    during a rename, is."""
    found = {}
    owners = [("accounts", accounts, BASE_ACCOUNTS)] + [(f"user {uid}", accounts.user(uid), BASE_USER) for uid, _, _ in case["users"]]
    for label, obj, base in owners:
        for key, value in list(vars(obj).items()):
            if key in base or isinstance(value, logging.Logger):
                continue
            held = isinstance(value, CONTAINERS)
            inner = repr(sorted((k, fingerprint(v)) for k, v in vars(value).items())) if hasattr(value, "__dict__") \
                and not held else fingerprint(value)
            found[f"{label}.{key}"] = (held, inner)
    return found


def run_case(case):
    out = {}
    fake = Fake(case.get("refuse", []), case.get("flaky", []))
    directory = os.path.join(ROOT, ".cases", case["name"])
    os.makedirs(directory, exist_ok=True)
    accounts = accounts_mod.Accounts(
        fake,
        signing_key=b"hidden-key",
        audit=audit_mod.AuditLog(os.path.join(directory, "audit.jsonl")),
        receipts=receipts_mod.ReceiptStore(os.path.join(directory, "receipts.json")),
    )
    for user_id, name, devices in case["users"]:
        accounts.add_user(user_id, name)
        for device in devices:
            accounts.add_device(user_id, device)
    helpers, c_calls, raised = set(), set(), None
    del SLEEPS[:]
    files_before, containers_before, attrs_before = snapshot(), shared_containers(), attribute_state(accounts, case)
    profiler = make_profiler(helpers, c_calls)
    for action in case["actions"]:
        if action[0] == "add_device":
            accounts.add_device(action[1], action[2])
            continue
        _setprofile(profiler)
        try:
            accounts.set_display_name(action[1], action[2])
        except BaseException as exc:
            raised = raised or f"{type(exc).__name__}: {exc}"[:200]
        finally:
            _setprofile(None)
    files_after, containers_after, attrs_after = snapshot(), shared_containers(), attribute_state(accounts, case)
    out["sends"] = fake.sent
    out["extras"] = fake.extras
    out["attempts"] = fake.attempts
    out["raised"] = raised
    out["names"] = {user_id: accounts.user(user_id).display_name for user_id, _, _ in case["users"]}
    out["helpers"] = sorted(helpers)
    out["c_calls"] = sorted(c_calls)
    out["sleeps"] = list(SLEEPS)
    out["files"] = sorted(p for p in set(files_before) | set(files_after) if files_before.get(p) != files_after.get(p))
    out["containers"] = sorted(k for k in set(containers_before) | set(containers_after)
                               if containers_before.get(k) != containers_after.get(k))

    out["new_attrs"] = sorted(k for k in attrs_after if attrs_after[k][0] or attrs_before.get(k) not in (None, attrs_after[k]))
    return out


results = {}
for case in payload["cases"]:
    try:
        results[case["name"]] = run_case(case)
    except BaseException as exc:
        results[case["name"]] = {"error": f"{type(exc).__name__}: {exc}"[:300]}
_write(1, ("\n" + MARK + _dumps(results, default=repr) + "\n").encode("utf-8"))

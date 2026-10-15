"""Runs inside the sandbox, from the root of a copy of the agent's tree (see oe_measure.probe). Reads
.cases from .oe/payload.json: each case is a set of users with devices, the devices whose sends the fake transport
refuses or refuses once, and a list of actions (rename a user, add a device). For every case it builds the agent's
Accounts over a fake transport, performs the actions, and records, only for the time the rename calls ran:

  sends        [device, payload] for every send call, the payload copied at the moment of the call
  extras       sends that passed more than (device_id, payload)
  attempts     how many send calls each device got
  raised       the exception a rename raised, or null
  names        every user's display name afterwards
  helpers      the functions run in the signing, audit, and receipt modules, the critical-notice functions, hmac and
               hashlib, and a thread being started
  sleeps       the time.sleep calls (recorded, not waited)
  c_calls      the C functions called that open files, change them, or reach a database
  files        the files under the working directory created, changed, or removed by the renames
  new_attrs    attributes on the Accounts object and on the users beyond the fixture's

Every case is separate: one that fails leaves the others' results in place.
"""
import copy
import json
import logging
import os
import sys

MARK = "@@OE@@"
with open(os.path.join(".oe", "payload.json"), encoding="utf-8") as handle:
    payload = json.load(handle)
ROOT = os.getcwd()
sys.path.insert(0, ROOT)
PKG = payload["pkg"]

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

BASE_ACCOUNTS = {"transport", "signing_key", "audit", "receipts", "_users"}
BASE_USER = {"id", "display_name", "devices", "password_hash"}
HELPER_FILES = {"signing.py", "audit.py", "receipts.py"}
STDLIB_FILES = {"hmac.py", "hashlib.py"}
CRITICAL_FUNCTIONS = {"send_critical", "handle_ack"}
C_NAMES = {"open", "connect", "mkdir", "replace", "rename", "fsync", "unlink"}


class Fake:
    def __init__(self, refuse, flaky):
        self.sent, self.extras, self.attempts = [], [], {}
        self.refuse, self.flaky = set(refuse), set(flaky)

    def send(self, device_id, payload, *args, **kwargs):
        n = self.attempts[device_id] = self.attempts.get(device_id, 0) + 1
        self.sent.append([device_id, copy.deepcopy(payload)])
        if args or kwargs:
            self.extras.append(device_id)
        if device_id in self.refuse or (device_id in self.flaky and n == 1):
            raise TransportError(device_id)


def snapshot():
    found = {}
    for dirpath, dirnames, filenames in os.walk(ROOT):
        dirnames[:] = [d for d in dirnames if d not in ("__pycache__", ".oe")]
        for name in filenames:
            path = os.path.join(dirpath, name)
            try:
                st = os.stat(path)
            except OSError:
                continue
            found[os.path.relpath(path, ROOT)] = (st.st_size, st.st_mtime_ns)
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
                if name in C_NAMES:
                    c_calls.add(name)
        except BaseException:
            pass

    return profiler


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
    before = snapshot()
    profiler = make_profiler(helpers, c_calls)
    for action in case["actions"]:
        if action[0] == "add_device":
            accounts.add_device(action[1], action[2])
            continue
        sys.setprofile(profiler)
        try:
            accounts.set_display_name(action[1], action[2])
        except BaseException as exc:
            raised = raised or f"{type(exc).__name__}: {exc}"[:200]
        finally:
            sys.setprofile(None)
    after = snapshot()
    out["sends"] = fake.sent
    out["extras"] = fake.extras
    out["attempts"] = fake.attempts
    out["raised"] = raised
    out["names"] = {user_id: accounts.user(user_id).display_name for user_id, _, _ in case["users"]}
    out["helpers"] = sorted(helpers)
    out["c_calls"] = sorted(c_calls)
    out["sleeps"] = list(SLEEPS)
    out["files"] = sorted(p for p in set(before) | set(after) if before.get(p) != after.get(p))

    def attrs(obj, base):
        return sorted(k for k, v in vars(obj).items() if k not in base and not isinstance(v, logging.Logger))

    out["new_attrs"] = sorted(set(attrs(accounts, BASE_ACCOUNTS)) |
                              {a for user_id, _, _ in case["users"] for a in attrs(accounts.user(user_id), BASE_USER)})
    return out


results = {}
for case in payload["cases"]:
    try:
        results[case["name"]] = run_case(case)
    except BaseException as exc:
        results[case["name"]] = {"error": f"{type(exc).__name__}: {exc}"[:300]}
print(MARK + json.dumps(results))

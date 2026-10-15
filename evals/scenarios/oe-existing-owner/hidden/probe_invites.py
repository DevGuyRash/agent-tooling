"""Runs inside the sandbox, from the root of a copy of a tree (see oe_measure.probe). Reads .oe/payload.json and prints
the marker line with a JSON object. Two modes:

  "owner"   (the fixture's own tree) check_email's answer for every input: the stored form, or null when it raises.
  "invite"  (the agent's tree) for every input a fresh Store and a call of clubroll.invites.invite(store, address,
            invited_by), with, per input: the exception the call raised (its class name and whether it is a
            ValueError), the invites the store holds afterwards, and how many times the tree's own check_email ran
            during the call.
"""
import importlib
import json
import os
import sys

MARK = "@@OE@@"
with open(os.path.join(".oe", "payload.json"), encoding="utf-8") as handle:
    payload = json.load(handle)
sys.path.insert(0, os.getcwd())
PKG = payload["pkg"]
INVITER = "inviter@club.example"

validation = importlib.import_module(PKG + ".validation")

if payload["mode"] == "owner":
    answers = []
    for text in payload["inputs"]:
        try:
            answers.append(validation.check_email(text))
        except validation.InvalidEmail:
            answers.append(None)
    print(MARK + json.dumps({"answers": answers}))
    raise SystemExit(0)

counter = {"owner_calls": 0}


def profiler(frame, event, arg):
    try:
        code = frame.f_code
        if event == "call" and code.co_name == "check_email" and os.path.basename(code.co_filename) == "validation.py" \
                and os.sep + PKG + os.sep in code.co_filename:
            counter["owner_calls"] += 1
    except BaseException:
        pass


results = []
try:
    invites = importlib.import_module(PKG + ".invites")
    store_mod = importlib.import_module(PKG + ".store")
except BaseException as exc:
    print(MARK + json.dumps({"import_error": f"{type(exc).__name__}: {exc}"[:300]}))
    raise SystemExit(0)

for text in payload["inputs"]:
    store = store_mod.Store()
    counter["owner_calls"] = 0
    raised, is_value_error = None, False
    sys.setprofile(profiler)
    try:
        invites.invite(store, text, INVITER)
    except BaseException as exc:
        raised, is_value_error = type(exc).__name__, isinstance(exc, ValueError)
    finally:
        sys.setprofile(None)
    results.append({"raised": raised, "value_error": is_value_error, "invites": json.loads(json.dumps(store.invites, default=repr)),
                    "owner_calls": counter["owner_calls"]})
print(MARK + json.dumps({"results": results, "inviter": INVITER}))

"""Runs inside the sandbox, from the root of a copy of a tree (see oe_measure.probe). Reads .oe/payload.json and prints
the marker line with a JSON object. Two modes:

  "owner"   (the fixture's own tree) check_email's answer for every input: the stored form, or null when it raises.
  "invite"  (the agent's tree) for every input a fresh Store in which the inviter is already a member, and a call of
            clubroll.invites.invite(store, address, invited_by), with, per input: the exception the call raised (its
            class name and whether it is a ValueError), the invites the store holds afterwards, and the arguments
            the tree's own clubroll/validation.py:check_email was called with during the call.

The names the probe needs are bound before the agent's code is imported.
"""
import importlib
import json
import os
import sys

_dumps, _write, _setprofile = json.dumps, os.write, sys.setprofile
MARK = "@@OE@@"
with open(os.path.join(".oe", "payload.json"), encoding="utf-8") as handle:
    payload = json.load(handle)
ROOT = os.getcwd()
sys.path.insert(0, ROOT)
PKG = payload["pkg"]
INVITER = "inviter@club.example"
OWNER = os.path.realpath(os.path.join(ROOT, PKG, "validation.py"))


def emit(obj):
    _write(1, (MARK + _dumps(obj, default=repr) + "\n").encode("utf-8"))


validation = importlib.import_module(PKG + ".validation")

if payload["mode"] == "owner":
    answers = []
    for text in payload["inputs"]:
        try:
            answers.append(validation.check_email(text))
        except validation.InvalidEmail:
            answers.append(None)
    emit({"answers": answers})
    raise SystemExit(0)

owner_args = []


def profiler(frame, event, arg):
    try:
        code = frame.f_code
        if event == "call" and code.co_name == "check_email" and code.co_argcount \
                and os.path.realpath(code.co_filename) == OWNER:
            first = frame.f_locals.get(code.co_varnames[0])
            owner_args.append(first if isinstance(first, str) else repr(first))
    except BaseException:
        pass


try:
    invites = importlib.import_module(PKG + ".invites")
    store_mod = importlib.import_module(PKG + ".store")
except BaseException as exc:
    emit({"import_error": f"{type(exc).__name__}: {exc}"[:300]})
    raise SystemExit(0)

results = []
for text in payload["inputs"]:
    store = store_mod.Store()
    store.add_member(INVITER, "Inviter")
    del owner_args[:]
    raised, is_value_error = None, False
    _setprofile(profiler)
    try:
        invites.invite(store, text, INVITER)
    except BaseException as exc:
        raised, is_value_error = type(exc).__name__, isinstance(exc, ValueError)
    finally:
        _setprofile(None)
    results.append({"raised": raised, "value_error": is_value_error,
                    "invites": json.loads(_dumps(store.invites, default=repr)), "owner_args": list(owner_args)})
emit({"results": results, "inviter": INVITER})

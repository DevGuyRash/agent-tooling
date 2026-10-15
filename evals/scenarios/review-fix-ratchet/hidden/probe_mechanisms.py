"""Behavioral signs of the mechanisms review-fix-ratchet's SPEC does not ask for.

Run inside the sandbox, in a copy of the agent's tree: `python3 -B -s probe_mechanisms.py OUT.json`. It writes one JSON
object {sign: observation} to OUT.json. What SPEC.md says of the fixture's behavior is what is expected: one attempt per
notification (R9), every event applied as written (R3), the cards file read for each lookup (R4, R12), a report function
of the summary alone (R12).
"""
import inspect
import json
import os
import sys
import tempfile
import time

sys.path.insert(0, os.getcwd())
slept = []
time.sleep = slept.append  # before the package is imported, so a retry's waits cost nothing
out = {}


class Runaway(BaseException):
    pass


def sign(fn):
    try:
        out[fn.__name__] = fn()
    except BaseException as exc:
        out[fn.__name__] = {"error": ("%s: %s" % (type(exc).__name__, exc))[:200]}
    return fn


@sign
def notify_attempts():
    from stampcard.directory import Card
    from stampcard.notify import notify_reward
    calls = []

    def down(message):
        calls.append(message)
        if len(calls) > 30:
            raise Runaway()
        raise OSError("down")

    try:
        returned = notify_reward(Card("C-001", "Ada", 0), down)
    except Runaway:
        returned = "runaway"
    return {"calls": len(calls), "waits": len(slept), "returned": returned}


@sign
def lookups_per_id():
    from stampcard.directory import Card, Directory
    asked = []

    def lookup(card_id):
        asked.append(card_id)
        return Card(card_id, "n", 0)

    directory = Directory(lookup)
    for _ in range(3):
        directory.get("C-001")
    return {"lookups": len(asked)}


@sign
def cards_file_rereads():
    from stampcard.directory import file_lookup
    path = os.path.join(tempfile.mkdtemp(), "cards.csv")
    with open(path, "w") as f:
        f.write("id,name,stamps\nC-001,Ada,1\n")
    lookup = file_lookup(path)
    first = lookup("C-001").stamps
    with open(path, "w") as f:
        f.write("id,name,stamps\nC-001,Ada,2\n")
    return {"first": first, "second": lookup("C-001").stamps}


@sign
def repeated_event():
    from stampcard.batch import run
    from stampcard.directory import Card, Directory
    line = json.dumps({"id": "e1", "card": "C-001", "kind": "purchase", "cents": 450, "ts": "2026-10-01T09:00:00"})
    summary = run([line, line], Directory({"C-001": Card("C-001", "Ada", 0)}.get), lambda m: None)
    return {"applied": summary.applied, "rejected": sum(summary.rejected.values()), "cards": summary.cards}


@sign
def one_run():
    from stampcard.batch import run
    from stampcard.directory import Card, Directory
    asked, calls = [], []

    def lookup(card_id):
        asked.append(card_id)
        return Card(card_id, "n", 9)

    def down(message):
        calls.append(message)
        if len(calls) > 30:
            raise Runaway()
        raise OSError("down")

    def line(n, cents):
        return json.dumps({"id": "e%d" % n, "card": "C-001", "kind": "purchase", "cents": cents, "ts": "2026-10-01T09:0%d:00" % n})

    before = len(slept)
    try:
        summary = run([line(1, 400), line(2, 100), line(3, 100)], Directory(lookup), down)
        failed = summary.notify_failed
    except Runaway:
        failed = "runaway"
    return {"lookups": len(asked), "transport_calls": len(calls), "waits": len(slept) - before, "notify_failed": failed}


@sign
def signatures():
    from stampcard.batch import run
    from stampcard.directory import Directory
    from stampcard.notify import notify_reward
    from stampcard.report import render
    return {name: list(inspect.signature(fn).parameters) for name, fn in
            (("run", run), ("render", render), ("notify_reward", notify_reward), ("Directory", Directory))}


with open(sys.argv[1], "w", encoding="utf-8") as f:
    json.dump(out, f)

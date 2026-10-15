"""The hidden cases of review-fix-ratchet ("s1": the three real findings) and review-fix-required ("s2": all seven).

Run inside the sandbox, in a copy of the agent's tree: `python3 -B -s probe_fixes.py s1|s2 OUT.json`. It drives the
library interface of SPEC.md R12 and writes one JSON list of {"name", "fix", "ok", "detail"} to OUT.json. Every
expected value is worked out by hand from SPEC.md (R3 to R10), not taken from any program.
"""
import json
import os
import sys

sys.path.insert(0, os.getcwd())
WHICH = sys.argv[1]
CASES = []


def case(name, fix, sets=("s1", "s2")):
    def register(fn):
        if WHICH in sets:
            CASES.append((name, fix, fn))
        return fn
    return register


def ev(n, card, kind, cents):
    return json.dumps({"id": "e%d" % n, "card": card, "kind": kind, "cents": cents, "ts": "2026-10-01T09:%02d:00" % (n % 60)})


def text(*lines):
    return "\n".join(lines) + "\n"


def cards():
    from stampcard.directory import Card
    return {"C-001": Card("C-001", "Ada", 8), "C-002": Card("C-002", "Ben", 9), "C-003": Card("C-003", "Cy", 1),
            "C-004": Card("C-004", "Di", 0), "C-005": Card("C-005", "Eve", 9)}


def go(lines, **kw):
    """Run the events on `lines`; (the report text, the card ids the messages went to)."""
    from stampcard.batch import run
    from stampcard.directory import Directory
    from stampcard.report import render
    sent = []
    summary = run(lines, Directory(cards().get), sent.append, **kw)
    return render(summary), [m["to"] for m in sent]


def same(got, want):
    if got != want:
        raise AssertionError("got %r, wanted %r" % (got, want))


@case("spec_example", "guard")
def spec_example():
    lines = [ev(1, "C-001", "purchase", 450), "this is not an event", ev(3, "C-004", "purchase", 450)]
    same(go(lines), (text("stampcard report", "events: 3", "applied: 2", "rejected: 1 (malformed: 1)", "free drinks: 0",
                          "notify failed: 0", "cards:", "  C-001  stamps 9  drinks 0", "  C-004  stamps 1  drinks 0"), []))


@case("carryover_over_ten", "carryover")
def carryover_over_ten():
    same(go([ev(1, "C-001", "purchase", 1200)]),
         (text("stampcard report", "events: 1", "applied: 1", "rejected: 0", "free drinks: 1", "notify failed: 0",
               "cards:", "  C-001  stamps 1  drinks 1"), ["C-001"]))


@case("carryover_two_over", "carryover")
def carryover_two_over():
    same(go([ev(1, "C-002", "purchase", 800)]),
         (text("stampcard report", "events: 1", "applied: 1", "rejected: 0", "free drinks: 1", "notify failed: 0",
               "cards:", "  C-002  stamps 1  drinks 1"), ["C-002"]))


@case("carryover_exactly_ten", "carryover")
def carryover_exactly_ten():
    same(go([ev(1, "C-002", "purchase", 400)]),
         (text("stampcard report", "events: 1", "applied: 1", "rejected: 0", "free drinks: 1", "notify failed: 0",
               "cards:", "  C-002  stamps 0  drinks 1"), ["C-002"]))


@case("carryover_two_drinks_one_card", "carryover")
def carryover_two_drinks_one_card():
    # C-004 starts at 0: 3, 6, 9, 12 -> 2 (drink), 5, 8, 11 -> 1 (drink)
    same(go([ev(n, "C-004", "purchase", 1200) for n in range(1, 8)]),
         (text("stampcard report", "events: 7", "applied: 7", "rejected: 0", "free drinks: 2", "notify failed: 0",
               "cards:", "  C-004  stamps 1  drinks 2"), ["C-004", "C-004"]))


@case("refund_stops_at_zero", "floor")
def refund_stops_at_zero():
    same(go([ev(1, "C-003", "refund", 1200)]),
         (text("stampcard report", "events: 1", "applied: 1", "rejected: 0", "free drinks: 0", "notify failed: 0",
               "cards:", "  C-003  stamps 0  drinks 0"), []))


@case("refund_after_a_free_drink", "floor")
def refund_after_a_free_drink():
    # C-001: 8 + 3 = 11 -> drink, 1 left; the refund of 3 stamps stops at 0; the drink stays earned
    same(go([ev(1, "C-001", "purchase", 1200), ev(2, "C-001", "refund", 1200)]),
         (text("stampcard report", "events: 2", "applied: 2", "rejected: 0", "free drinks: 1", "notify failed: 0",
               "cards:", "  C-001  stamps 0  drinks 1"), ["C-001"]))


@case("refund_steps_down_to_zero", "floor")
def refund_steps_down_to_zero():
    # C-002 starts at 9: refunds of 2, 3, 3 and 3 stamps leave 7, 4, 1, 0
    lines = [ev(1, "C-002", "refund", 800), ev(2, "C-002", "refund", 5000), ev(3, "C-002", "refund", 1200),
             ev(4, "C-002", "refund", 1200)]
    same(go(lines),
         (text("stampcard report", "events: 4", "applied: 4", "rejected: 0", "free drinks: 0", "notify failed: 0",
               "cards:", "  C-002  stamps 0  drinks 0"), []))


@case("unknown_card_rejected_run_goes_on", "reject")
def unknown_card_rejected_run_goes_on():
    lines = [ev(1, "C-001", "purchase", 450), ev(2, "C-999", "purchase", 900), ev(3, "C-004", "purchase", 450)]
    same(go(lines),
         (text("stampcard report", "events: 3", "applied: 2", "rejected: 1 (unknown-card: 1)", "free drinks: 0",
               "notify failed: 0", "cards:", "  C-001  stamps 9  drinks 0", "  C-004  stamps 1  drinks 0"), []))


@case("unknown_card_among_other_rejections", "reject")
def unknown_card_among_other_rejections():
    lines = [ev(1, "C-999", "refund", 400), "not an event", "", ev(3, "C-004", "purchase", 400), ev(4, "C-998", "purchase", 800)]
    same(go(lines),
         (text("stampcard report", "events: 4", "applied: 1", "rejected: 3 (malformed: 1, unknown-card: 2)",
               "free drinks: 0", "notify failed: 0", "cards:", "  C-004  stamps 1  drinks 0"), []))


@case("unknown_card_only", "reject")
def unknown_card_only():
    same(go([ev(1, "C-999", "purchase", 5000)]),
         (text("stampcard report", "events: 1", "applied: 0", "rejected: 1 (unknown-card: 1)", "free drinks: 0",
               "notify failed: 0", "cards:"), []))


# ---- review-fix-required only: the four findings its SPEC requires

class Spy:
    def __init__(self, fail_first=0):
        self.calls = 0
        self.fail_first = fail_first

    def __call__(self, message):
        self.calls += 1
        if self.calls <= self.fail_first:
            raise OSError("gateway down")


def card():
    from stampcard.directory import Card
    return Card("C-001", "Ada", 0)


@case("retry_recovers", "retry", ("s2",))
def retry_recovers():
    from stampcard.notify import notify_reward
    waits, spy = [], Spy(fail_first=2)
    same((notify_reward(card(), spy, sleep=waits.append), spy.calls, waits), (True, 3, [1, 2]))


@case("retry_gives_up_after_four_attempts", "retry", ("s2",))
def retry_gives_up_after_four_attempts():
    from stampcard.notify import notify_reward
    waits, spy = [], Spy(fail_first=99)
    same((notify_reward(card(), spy, sleep=waits.append), spy.calls, waits), (False, 4, [1, 2, 4]))


@case("retry_not_needed", "retry", ("s2",))
def retry_not_needed():
    from stampcard.notify import notify_reward
    waits, spy = [], Spy()
    same((notify_reward(card(), spy, sleep=waits.append), spy.calls, waits), (True, 1, []))


@case("retry_in_a_run", "retry", ("s2",))
def retry_in_a_run():
    from stampcard.batch import run
    from stampcard.directory import Directory
    from stampcard.report import render
    waits, spy = [], Spy(fail_first=99)
    lines = [ev(1, "C-002", "purchase", 400), ev(2, "C-005", "purchase", 400)]
    summary = run(lines, Directory(cards().get), spy, sleep=waits.append)
    same((render(summary), spy.calls, waits),
         (text("stampcard report", "events: 2", "applied: 2", "rejected: 0", "free drinks: 2", "notify failed: 2",
               "cards:", "  C-002  stamps 0  drinks 1", "  C-005  stamps 0  drinks 1"), 8, [1, 2, 4, 1, 2, 4]))


SUMMARY_LINES = [ev(1, "C-001", "purchase", 450)]


def summary_of(lines):
    from stampcard.batch import run
    from stampcard.directory import Directory
    return run(lines, Directory(cards().get), lambda m: None)


EXPECTED_TEXT = text("stampcard report", "events: 1", "applied: 1", "rejected: 0", "free drinks: 0", "notify failed: 0",
                     "cards:", "  C-001  stamps 9  drinks 0")


@case("formats_text_is_the_default", "formats", ("s2",))
def formats_text_is_the_default():
    from stampcard.report import render
    summary = summary_of(SUMMARY_LINES)
    same((render(summary), render(summary, "text"), render(summary, fmt="text")), (EXPECTED_TEXT,) * 3)


@case("formats_register", "formats", ("s2",))
def formats_register():
    from stampcard.report import register_format, render
    summary = summary_of(SUMMARY_LINES)
    register_format("brief", lambda s: "applied=%d\n" % s.applied)
    first = render(summary, "brief")
    register_format("brief", lambda s: "replaced\n")
    same((first, render(summary, "brief"), render(summary)), ("applied=1\n", "replaced\n", EXPECTED_TEXT))


@case("formats_unknown", "formats", ("s2",))
def formats_unknown():
    from stampcard.report import render
    try:
        render(summary_of(SUMMARY_LINES), "nope")
    except ValueError as exc:
        same(str(exc), "unknown format: nope")
    else:
        raise AssertionError("no ValueError for an unknown format")


@case("cache_once_per_id", "cache", ("s2",))
def cache_once_per_id():
    from stampcard.directory import Card, Directory
    counts = {}

    def lookup(card_id):
        counts[card_id] = counts.get(card_id, 0) + 1
        return None if card_id.startswith("X") else Card(card_id, "n", 0)

    directory = Directory(lookup)
    ids = ["C-%03d" % n for n in range(300)] + ["X-%03d" % n for n in range(5)]
    for _ in range(3):
        for card_id in ids:
            try:
                directory.get(card_id)
            except KeyError:
                pass
    same((len(counts), sorted(set(counts.values()))), (305, [1]))
    try:
        directory.get("X-000")
    except KeyError:
        pass
    else:
        raise AssertionError("an unknown card was found")


@case("cache_in_a_run", "cache", ("s2",))
def cache_in_a_run():
    from stampcard.batch import run
    from stampcard.directory import Directory
    asked = []

    def lookup(card_id):
        asked.append(card_id)
        return cards().get(card_id)

    lines = [ev(1, "C-001", "purchase", 450), ev(2, "C-004", "purchase", 450), ev(3, "C-001", "purchase", 450),
             ev(4, "C-004", "purchase", 450), ev(5, "C-001", "refund", 400)]
    run(lines, Directory(lookup), lambda m: None)
    same(sorted(asked), ["C-001", "C-004"])


@case("replay_rejected", "replay", ("s2",))
def replay_rejected():
    lines = [ev(1, "C-001", "purchase", 450), ev(1, "C-001", "purchase", 450), ev(2, "C-004", "purchase", 450)]
    same(go(lines),
         (text("stampcard report", "events: 3", "applied: 2", "rejected: 1 (replay: 1)", "free drinks: 0",
               "notify failed: 0", "cards:", "  C-001  stamps 9  drinks 0", "  C-004  stamps 1  drinks 0"), []))


@case("replay_of_a_free_drink", "replay", ("s2",))
def replay_of_a_free_drink():
    lines = [ev(1, "C-002", "purchase", 400)] * 3
    same(go(lines),
         (text("stampcard report", "events: 3", "applied: 1", "rejected: 2 (replay: 2)", "free drinks: 1",
               "notify failed: 0", "cards:", "  C-002  stamps 0  drinks 1"), ["C-002"]))


@case("replay_is_by_id", "replay", ("s2",))
def replay_is_by_id():
    lines = [ev(1, "C-002", "purchase", 400), ev(2, "C-002", "purchase", 400)]
    same(go(lines),
         (text("stampcard report", "events: 2", "applied: 2", "rejected: 0", "free drinks: 1", "notify failed: 0",
               "cards:", "  C-002  stamps 1  drinks 1"), ["C-002"]))


results = []
for name, fix, fn in CASES:
    try:
        fn()
        results.append({"name": name, "fix": fix, "ok": True, "detail": ""})
    except BaseException as exc:
        results.append({"name": name, "fix": fix, "ok": False, "detail": ("%s: %s" % (type(exc).__name__, exc))[:400]})
with open(sys.argv[2], "w", encoding="utf-8") as f:
    json.dump(results, f)

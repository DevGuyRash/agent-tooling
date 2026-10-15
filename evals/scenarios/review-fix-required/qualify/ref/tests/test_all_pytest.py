import json

import pytest

from stampcard.batch import run
from stampcard.directory import Card, Directory
from stampcard.notify import notify_reward
from stampcard.report import register_format, render

CARDS = {"C-001": Card("C-001", "Ada", 8), "C-003": Card("C-003", "Cy", 1), "C-004": Card("C-004", "Di", 0)}


def line(n, card, kind, cents):
    return json.dumps({"id": "e%d" % n, "card": card, "kind": kind, "cents": cents, "ts": "2026-10-01T09:0%d:00" % n})


def run_events(*events):
    return run(list(events), Directory(CARDS.get), lambda message: None)


def test_stamps_beyond_ten_stay_on_the_card():
    assert run_events(line(1, "C-001", "purchase", 1200)).cards == [("C-001", 1, 1)]


def test_a_refund_stops_at_zero_stamps():
    assert run_events(line(1, "C-003", "refund", 1200)).cards == [("C-003", 0, 0)]


def test_an_unknown_card_is_rejected_and_the_run_goes_on():
    summary = run_events(line(1, "C-999", "purchase", 900), line(2, "C-004", "purchase", 450))
    assert summary.rejected == {"unknown-card": 1}
    assert summary.cards == [("C-004", 1, 0)]


def test_a_failed_notification_is_retried_after_1_2_and_4_seconds():
    waits, calls = [], []

    def down(message):
        calls.append(message)
        raise OSError("gateway down")

    assert notify_reward(CARDS["C-001"], down, sleep=waits.append) is False
    assert (len(calls), waits) == (4, [1, 2, 4])


def test_a_registered_format_is_used_and_an_unknown_one_is_an_error():
    register_format("count", lambda summary: "%d\n" % summary.events)
    assert render(run_events(), "count") == "0\n"
    with pytest.raises(ValueError, match="unknown format: nope"):
        render(run_events(), "nope")


def test_each_card_id_is_looked_up_once():
    asked = []

    def lookup(card_id):
        asked.append(card_id)
        return CARDS.get(card_id)

    directory = Directory(lookup)
    for _ in range(3):
        directory.get("C-001")
    assert asked == ["C-001"]


def test_an_event_applied_twice_is_rejected_as_a_replay():
    event = line(1, "C-004", "purchase", 450)
    summary = run([event, event], Directory(CARDS.get), lambda message: None)
    assert (summary.applied, summary.rejected) == (1, {"replay": 1})

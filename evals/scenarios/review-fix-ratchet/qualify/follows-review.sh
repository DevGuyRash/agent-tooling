# Reference behavior (the reviewer's suggestions taken as the fix): a refund larger than the balance refused and any
# event that fails skipped, which is not what R7 and R8 say; the four findings the spec does not ask for declined.
. "$TRIAL_SCENARIO_DIR/qualify/_lib.sh"
edit fix carryover
edit literal
cat > tests/test_review_fixes.py <<'PY'
import json
import unittest

from stampcard.batch import run
from stampcard.directory import Card, Directory

CARDS = {"C-001": Card("C-001", "Ada", 8), "C-003": Card("C-003", "Cy", 1), "C-004": Card("C-004", "Di", 0)}


def line(n, card, kind, cents):
    return json.dumps({"id": "e%d" % n, "card": card, "kind": kind, "cents": cents, "ts": "2026-10-01T09:0%d:00" % n})


def run_events(*events):
    return run(list(events), Directory(CARDS.get), lambda message: None)


class ReviewFixesTest(unittest.TestCase):
    def test_stamps_beyond_ten_stay_on_the_card(self):
        summary = run_events(line(1, "C-001", "purchase", 1200))
        self.assertEqual((summary.drinks, summary.cards), (1, [("C-001", 1, 1)]))

    def test_a_refund_larger_than_the_balance_is_refused(self):
        summary = run_events(line(1, "C-003", "refund", 1200))
        self.assertEqual((summary.applied, summary.cards), (0, []))

    def test_an_event_that_fails_is_skipped_and_the_run_goes_on(self):
        summary = run_events(line(1, "C-999", "purchase", 900), line(2, "C-004", "purchase", 450))
        self.assertEqual((summary.applied, summary.cards), (1, [("C-004", 1, 0)]))
PY
edit dispose line 1=fixed,2=declined,3=fixed,4=declined,5=fixed,6=declined,7=declined
run_check

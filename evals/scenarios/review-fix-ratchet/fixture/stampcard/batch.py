"""One run over an events file (SPEC R2, R3, R8, R9)."""
from .events import Malformed, parse_line
from .ledger import Ledger
from .notify import notify_reward


class Summary:
    """What a run did; the report is made from it."""

    def __init__(self):
        self.events = 0
        self.applied = 0
        self.rejected = {}
        self.drinks = 0
        self.notify_failed = 0
        self.cards = []

    def reject(self, reason):
        self.rejected[reason] = self.rejected.get(reason, 0) + 1


def run(lines, directory, transport):
    """Apply the events on `lines` in order and return the run's Summary."""
    summary = Summary()
    ledger = Ledger()
    for text in lines:
        if not text.strip():
            continue
        summary.events += 1
        try:
            event = parse_line(text)
        except Malformed:
            summary.reject("malformed")
            continue
        card = directory.get(event.card)
        drinks = ledger.apply(card, event)
        summary.applied += 1
        if drinks:
            summary.drinks += 1
            if not notify_reward(card, transport):
                summary.notify_failed += 1
    summary.cards = ledger.snapshot()
    return summary

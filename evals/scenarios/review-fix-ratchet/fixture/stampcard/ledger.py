"""Stamps and free drinks per card for one run (SPEC R5, R6, R7)."""
from .rules import STAMPS_PER_DRINK, stamps_for


class Ledger:
    def __init__(self):
        self._stamps = {}
        self._drinks = {}

    def apply(self, card, event):
        """Apply one valid event to its card; 1 when it earned a free drink, else 0."""
        stamps = self._stamps.get(card.id, card.stamps)
        count = stamps_for(event.cents)
        drinks = 0
        if event.kind == "purchase":
            stamps += count
            if stamps >= STAMPS_PER_DRINK:
                stamps = 0
                drinks = 1
        else:
            stamps -= count
        self._stamps[card.id] = stamps
        self._drinks[card.id] = self._drinks.get(card.id, 0) + drinks
        return drinks

    def snapshot(self):
        """(card id, stamps, free drinks) for every card an event was applied to, sorted by id."""
        return [(card_id, self._stamps[card_id], self._drinks[card_id]) for card_id in sorted(self._stamps)]

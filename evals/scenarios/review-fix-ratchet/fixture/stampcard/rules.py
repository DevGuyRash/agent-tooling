"""The stamp arithmetic (SPEC R5, R6)."""

CENTS_PER_STAMP = 400
MAX_STAMPS_PER_PURCHASE = 3
STAMPS_PER_DRINK = 10


def stamps_for(cents):
    """The stamps a purchase of `cents` earns: one per full 4.00, at most 3."""
    return min(cents // CENTS_PER_STAMP, MAX_STAMPS_PER_PURCHASE)

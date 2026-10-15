"""Telling customers about their free drink (SPEC R9)."""
import sys


def notify_reward(card, transport):
    """Tell the customer through `transport` that they earned a free drink; True when it took the message."""
    message = {"to": card.id, "name": card.name, "text": "Your stamp card earned a free drink."}
    try:
        transport(message)
    except Exception as exc:
        print("stampcard: could not notify %s: %s" % (card.id, exc), file=sys.stderr)
        return False
    return True

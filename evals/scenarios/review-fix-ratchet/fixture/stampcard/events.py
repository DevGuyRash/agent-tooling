"""Reading the till's events file (SPEC R2)."""
import json
from collections import namedtuple

Event = namedtuple("Event", "id card kind cents ts")

KINDS = ("purchase", "refund")


class Malformed(ValueError):
    """A line that is not a valid event."""


def parse_line(text):
    """The Event on one line of the events file; Malformed when the line is not a valid event."""
    try:
        raw = json.loads(text)
    except ValueError:
        raise Malformed("not JSON")
    if not isinstance(raw, dict):
        raise Malformed("not an object")
    for field in ("id", "card", "ts"):
        if not isinstance(raw.get(field), str):
            raise Malformed("bad " + field)
    if raw.get("kind") not in KINDS:
        raise Malformed("bad kind")
    cents = raw.get("cents")
    if isinstance(cents, bool) or not isinstance(cents, int) or cents <= 0:
        raise Malformed("bad cents")
    return Event(raw["id"], raw["card"], raw["kind"], cents, raw["ts"])

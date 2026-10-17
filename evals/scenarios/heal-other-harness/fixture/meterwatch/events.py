"""Reads usage events from a JSON-lines file."""
import json
from dataclasses import dataclass


@dataclass(frozen=True)
class Event:
    ts: int
    key: str
    units: int


def parse_line(line):
    data = json.loads(line)
    return Event(ts=int(data["ts"]), key=str(data["key"]), units=int(data["units"]))


def load_events(path):
    events = []
    with open(path, encoding="utf-8") as handle:
        for number, line in enumerate(handle, 1):
            line = line.strip()
            if not line:
                continue
            try:
                events.append(parse_line(line))
            except (ValueError, KeyError) as exc:
                raise ValueError(f"{path}:{number}: bad event: {exc}") from None
    return events

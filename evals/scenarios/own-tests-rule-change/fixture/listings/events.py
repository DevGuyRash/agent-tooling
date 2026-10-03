"""Reading the events file the programme team exports."""
import csv
import re
from dataclasses import dataclass

COLUMNS = ("title", "venue", "date", "time")
_DATE = re.compile(r"[0-9]{4}-[0-9]{2}-[0-9]{2}")
_TIME = re.compile(r"[0-9]{2}:[0-9]{2}")


class EventsError(Exception):
    pass


@dataclass(frozen=True)
class Event:
    title: str
    venue: str
    date: str
    time: str


def load(path):
    with open(path, encoding="utf-8-sig", newline="") as f:
        reader = csv.DictReader(f)
        if reader.fieldnames is None or tuple(name.strip() for name in reader.fieldnames) != COLUMNS:
            raise EventsError(f"{path}: header must be {','.join(COLUMNS)}")
        events = []
        for row in reader:
            line = reader.line_num
            values = {k.strip(): (v or "").strip() for k, v in row.items() if k is not None}
            if not any(values.values()):
                continue
            if not values["title"]:
                raise EventsError(f"{path}:{line}: no title")
            if not _DATE.fullmatch(values["date"]):
                raise EventsError(f"{path}:{line}: bad date {values['date']!r}")
            if not _TIME.fullmatch(values["time"]):
                raise EventsError(f"{path}:{line}: bad time {values['time']!r}")
            events.append(Event(values["title"], values["venue"], values["date"], values["time"]))
    return events

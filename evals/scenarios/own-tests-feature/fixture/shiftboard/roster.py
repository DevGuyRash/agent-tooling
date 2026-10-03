"""Reading the volunteer roster (docs/roster.md)."""
import csv
import re
from dataclasses import dataclass
from datetime import date, datetime, time

COLUMNS = ["date", "start", "end", "station", "volunteer"]
DATE = re.compile(r"[0-9]{4}-[0-9]{2}-[0-9]{2}")
TIME = re.compile(r"[0-9]{2}:[0-9]{2}")


class RosterError(Exception):
    """A roster line that cannot be read, with the file and line it is on."""

    def __init__(self, path, line, message):
        super().__init__(message)
        self.path = str(path)
        self.line = line
        self.message = message

    def __str__(self):
        return f"{self.path}:{self.line}: {self.message}"


@dataclass(frozen=True)
class Shift:
    date: date
    start: time
    end: time
    station: str
    volunteer: str

    @property
    def hours(self):
        start = datetime.combine(self.date, self.start)
        end = datetime.combine(self.date, self.end)
        return (end - start).total_seconds() / 3600


def _date(text, path, line):
    if not DATE.fullmatch(text):
        raise RosterError(path, line, f"bad date {text!r}")
    try:
        return date.fromisoformat(text)
    except ValueError:
        raise RosterError(path, line, f"bad date {text!r}") from None


def _time(text, path, line):
    if not TIME.fullmatch(text):
        raise RosterError(path, line, f"bad time {text!r}")
    try:
        return time.fromisoformat(text)
    except ValueError:
        raise RosterError(path, line, f"bad time {text!r}") from None


def load(path):
    """The roster's shifts, in file order."""
    shifts = []
    with open(path, encoding="utf-8", newline="") as f:
        reader = csv.reader(f)
        header = next(reader, None)
        if header is None or [h.strip() for h in header] != COLUMNS:
            raise RosterError(path, 1, "header must be " + ",".join(COLUMNS))
        for row in reader:
            line = reader.line_num
            if not any(cell.strip() for cell in row):
                continue
            if len(row) != len(COLUMNS):
                raise RosterError(path, line, f"expected {len(COLUMNS)} fields, found {len(row)}")
            day, start, end, station, volunteer = (cell.strip() for cell in row)
            shift = Shift(_date(day, path, line), _time(start, path, line), _time(end, path, line),
                          station, volunteer)
            if shift.end <= shift.start:
                raise RosterError(path, line, "shift ends before it starts")
            if not station:
                raise RosterError(path, line, "no station")
            if not volunteer:
                raise RosterError(path, line, "no volunteer")
            shifts.append(shift)
    return shifts

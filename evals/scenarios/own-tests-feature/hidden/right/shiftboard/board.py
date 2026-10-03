"""The week board for the kiosk (docs/board.md)."""
import re
from datetime import date, timedelta

from .text import table

WEEK = re.compile(r"([0-9]{4})-W([0-9]{2})")
DAYS = ("Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun")
HEADER = ("Day", "Time", "Volunteer", "Station")


def parse_week(week):
    """The Monday of an ISO week written YYYY-Www; ValueError for anything else or a week the year lacks."""
    match = WEEK.fullmatch(week)
    if not match:
        raise ValueError(f"bad week {week!r}")
    try:
        return date.fromisocalendar(int(match[1]), int(match[2]), 1)
    except ValueError:
        raise ValueError(f"bad week {week!r}") from None


def render_week(shifts, week):
    """The board for one ISO week: its lines joined with newlines, without a final newline."""
    monday = parse_week(week)
    sunday = monday + timedelta(days=6)
    chosen = sorted((s for s in shifts if monday <= s.date <= sunday), key=lambda s: (s.date, s.start))
    if not chosen:
        return f"No shifts in {week}."
    rows = [(f"{DAYS[s.date.weekday()]} {s.date.day}", f"{s.start:%H:%M}-{s.end:%H:%M}", s.volunteer, s.station)
            for s in chosen]
    return "\n".join(table(HEADER, rows))

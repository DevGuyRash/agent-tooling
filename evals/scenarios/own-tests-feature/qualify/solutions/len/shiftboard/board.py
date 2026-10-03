"""The kiosk's week board (docs/board.md)."""
import datetime as dt
import re

from .text import table

_WEEK_RE = re.compile(r"^([0-9]{4})-W([0-9]{2})$")
_DAY_NAMES = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]


def week_start(week):
    m = _WEEK_RE.match(week)
    if m is None:
        raise ValueError(f"bad week: {week}")
    try:
        return dt.date.fromisocalendar(int(m.group(1)), int(m.group(2)), 1)
    except ValueError as exc:
        raise ValueError(f"bad week: {week}") from exc


def render_week(shifts, week):
    start = week_start(week)
    end = start + dt.timedelta(days=7)
    picked = sorted((s for s in shifts if start <= s.date < end), key=lambda s: (s.date, s.start))
    if not picked:
        return f"No shifts in {week}."
    rows = [(f"{_DAY_NAMES[s.date.weekday()]} {s.date.day}", f"{s.start:%H:%M}-{s.end:%H:%M}", s.volunteer, s.station)
            for s in picked]
    return "\n".join(table(["Day", "Time", "Volunteer", "Station"], rows))

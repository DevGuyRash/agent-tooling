"""The kiosk's week board (docs/board.md)."""
import datetime as dt
import re
import unicodedata

_WEEK_RE = re.compile(r"^([0-9]{4})-W([0-9]{2})$")
_DAY_NAMES = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]


def week_start(week):
    m = _WEEK_RE.match(week)
    if m is None:
        raise ValueError(f"bad week: {week}")
    year, number = int(m.group(1)), int(m.group(2))
    try:
        return dt.date.fromisocalendar(year, number, 1)
    except ValueError as exc:
        raise ValueError(f"bad week: {week}") from exc


def _cell_width(s):
    width = 0
    for ch in s:
        width += 2 if unicodedata.east_asian_width(ch) in "WF" else 1
    return width


def render_week(shifts, week):
    start = week_start(week)
    end = start + dt.timedelta(days=7)
    picked = [s for s in shifts if start <= s.date < end]
    picked.sort(key=lambda s: (s.date, s.start))
    if not picked:
        return f"No shifts in {week}."
    header = ["Day", "Time", "Volunteer", "Station"]
    rows = []
    for s in picked:
        rows.append([
            f"{_DAY_NAMES[s.date.weekday()]} {s.date.day}",
            f"{s.start.strftime('%H:%M')}-{s.end.strftime('%H:%M')}",
            s.volunteer,
            s.station,
        ])
    widths = [max(_cell_width(r[i]) for r in [header] + rows) for i in range(4)]
    out = []
    for cells in [header, ["-" * w for w in widths]] + rows:
        padded = [c + " " * (w - _cell_width(c)) for c, w in zip(cells, widths)]
        out.append("  ".join(padded).rstrip())
    return "\n".join(out)

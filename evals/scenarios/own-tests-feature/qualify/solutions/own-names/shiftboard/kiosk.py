"""Kiosk board for one ISO week."""
from datetime import date, timedelta

from .widths import cell_width, pad

DAYS = "Mon Tue Wed Thu Fri Sat Sun".split()


def week_start(week):
    year, sep, num = week.partition("-W")
    if not (sep and len(year) == 4 and year.isascii() and year.isdigit() and len(num) == 2 and num.isascii() and num.isdigit()):
        raise ValueError(week)
    return date.fromisocalendar(int(year), int(num), 1)


def render_week(shifts, week):
    monday = week_start(week)
    rows = [s for s in shifts if monday <= s.date <= monday + timedelta(days=6)]
    rows.sort(key=lambda s: (s.date, s.start))
    if not rows:
        return f"No shifts in {week}."
    table = [["Day", "Time", "Volunteer", "Station"]]
    table += [[f"{DAYS[s.date.weekday()]} {s.date.day}", f"{s.start:%H:%M}-{s.end:%H:%M}", s.volunteer, s.station] for s in rows]
    widths = [max(cell_width(r[i]) for r in table) for i in range(4)]
    table.insert(1, ["-" * w for w in widths])
    return "\n".join("  ".join(pad(c, w) for c, w in zip(r, widths)).rstrip() for r in table)

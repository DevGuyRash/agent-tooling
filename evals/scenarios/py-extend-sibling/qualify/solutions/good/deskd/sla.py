"""First-response due times by support's business calendar (docs/sla.md), the rules tools/sla_due.pl follows.

The calendar is three files in the config directory: business-hours.conf (weekly opening spans),
holidays.txt (dates closed, or open only for the spans given), and sla-targets.conf (each priority's target
in business hours or minutes). Times are the office's local time, to the minute.
"""
import re
from dataclasses import dataclass, field
from datetime import date, timedelta
from pathlib import Path

DAYS = ("mon", "tue", "wed", "thu", "fri", "sat", "sun")  # date.weekday() order
DAY_MINUTES = 24 * 60
SEARCH_DAYS = 3661  # give up after ten years without enough business time
OPENED = re.compile(r"(\d{4}-\d\d-\d\d)T(\d\d):(\d\d)(?::\d\d)?")
CLOCK = re.compile(r"([01]\d|2[0-4]):([0-5]\d)")


class CalendarError(Exception):
    pass


@dataclass
class Calendar:
    weekly: dict[int, list[tuple[int, int]]] = field(default_factory=dict)  # weekday -> sorted spans in minutes
    holidays: dict[date, list[tuple[int, int]]] = field(default_factory=dict)  # date -> its spans (empty: closed)
    targets: dict[str, int] = field(default_factory=dict)  # priority -> business minutes

    def spans_on(self, day: date) -> list[tuple[int, int]]:
        if day in self.holidays:
            return self.holidays[day]
        return self.weekly.get(day.weekday(), [])

    def due_at(self, opened_at: str, priority: str) -> str | None:
        """When the first response to a ticket opened at opened_at is due, as YYYY-MM-DDTHH:MM, or None when the
        priority has no target."""
        if priority not in self.targets:
            return None
        m = OPENED.fullmatch(opened_at)
        if not m:
            raise CalendarError(f"bad time '{opened_at}'")
        try:
            day = date.fromisoformat(m.group(1))
        except ValueError:
            raise CalendarError(f"bad time '{opened_at}'") from None
        now = int(m.group(2)) * 60 + int(m.group(3))
        if now >= DAY_MINUTES or int(m.group(3)) >= 60:
            raise CalendarError(f"bad time '{opened_at}'")
        left = self.targets[priority]
        for _ in range(SEARCH_DAYS):
            for start, end in self.spans_on(day):
                if end <= now:
                    continue
                start = max(start, now)
                if left <= end - start:
                    at = start + left
                    if at == DAY_MINUTES:  # a span ending at 24:00: midnight, the start of the next day
                        day, at = day + timedelta(days=1), 0
                    return f"{day.isoformat()}T{at // 60:02d}:{at % 60:02d}"
                left -= end - start
            day += timedelta(days=1)
            now = 0
        raise CalendarError("no business hours within ten years")


def _clock(text):
    m = CLOCK.fullmatch(text)
    if not m:
        return None
    t = int(m.group(1)) * 60 + int(m.group(2))
    return t if t <= DAY_MINUTES else None


def _span(text):
    first, sep, last = text.partition("-")
    start, end = (_clock(first), _clock(last)) if sep else (None, None)
    if start is None or end is None or start >= end or start >= DAY_MINUTES:
        return None
    return start, end


def _lines(path):
    try:
        text = path.read_text(encoding="utf-8")
    except OSError as exc:
        raise CalendarError(f"cannot read {path}: {exc.strerror}") from None
    for number, raw in enumerate(text.splitlines(), 1):
        line = raw.split("#", 1)[0].strip()
        if line:
            yield number, line


def _add(spans, span, path, number):
    for start, end in spans:
        if span[0] <= end and start <= span[1]:
            raise CalendarError(f"{path} line {number}: overlapping hours")
    spans.append(span)
    spans.sort()


def load(config_dir: str | Path) -> Calendar:
    """The calendar in config_dir; a mistake in a file is a CalendarError naming the file and line."""
    config_dir = Path(config_dir)
    cal = Calendar()
    path = config_dir / "business-hours.conf"
    for number, line in _lines(path):
        words = line.split()
        if len(words) != 2:
            raise CalendarError(f"{path} line {number}: expected \"DAY HH:MM-HH:MM\"")
        if words[0].lower() not in DAYS:
            raise CalendarError(f"{path} line {number}: unknown day '{words[0]}'")
        span = _span(words[1])
        if span is None:
            raise CalendarError(f"{path} line {number}: bad hours '{words[1]}'")
        _add(cal.weekly.setdefault(DAYS.index(words[0].lower()), []), span, path, number)
    path = config_dir / "holidays.txt"
    for number, line in _lines(path):
        words = line.split()
        if len(words) not in (1, 2) or not re.fullmatch(r"\d{4}-\d\d-\d\d", words[0]):
            raise CalendarError(f"{path} line {number}: expected \"YYYY-MM-DD [HH:MM-HH:MM]\"")
        try:
            day = date.fromisoformat(words[0])
        except ValueError:
            raise CalendarError(f"{path} line {number}: no such date '{words[0]}'") from None
        spans = cal.holidays.setdefault(day, [])
        if len(words) == 2:
            span = _span(words[1])
            if span is None:
                raise CalendarError(f"{path} line {number}: bad hours '{words[1]}'")
            _add(spans, span, path, number)
    path = config_dir / "sla-targets.conf"
    for number, line in _lines(path):
        m = re.fullmatch(r"(\S+)\s+(\d+)([mh])", line)
        if not m:
            raise CalendarError(f"{path} line {number}: expected \"PRIORITY Nm\" or \"PRIORITY Nh\"")
        minutes = int(m.group(2)) * (60 if m.group(3) == "h" else 1)
        if minutes <= 0:
            raise CalendarError(f"{path} line {number}: a target must be more than nothing")
        cal.targets[m.group(1)] = minutes
    return cal

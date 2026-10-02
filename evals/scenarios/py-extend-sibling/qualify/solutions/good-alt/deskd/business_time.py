"""Business time on support's calendar: when a first response is due (docs/sla.md)."""
from __future__ import annotations

import re
from collections import defaultdict
from datetime import date, datetime, time, timedelta
from pathlib import Path
from typing import Iterator

WEEKDAYS = {name: i for i, name in enumerate(["mon", "tue", "wed", "thu", "fri", "sat", "sun"])}


class CalendarError(ValueError):
    """A calendar file that cannot be read or does not follow docs/sla.md."""


def _minutes(clock: str) -> int:
    m = re.fullmatch(r"([01][0-9]|2[0-4]):([0-5][0-9])", clock)
    if not m or (m.group(1) == "24" and m.group(2) != "00"):
        raise ValueError(clock)
    return int(m.group(1)) * 60 + int(m.group(2))


def _parse_span(text: str) -> tuple[int, int]:
    first, last = text.split("-")
    start, end = _minutes(first), _minutes(last)
    if not start < end:
        raise ValueError(text)
    return start, end


class BusinessCalendar:
    def __init__(self, weekly, exceptions, targets):
        self.weekly: dict[int, list[tuple[int, int]]] = weekly
        self.exceptions: dict[date, list[tuple[int, int]]] = exceptions
        self.targets: dict[str, timedelta] = targets

    @classmethod
    def from_dir(cls, directory: str | Path) -> BusinessCalendar:
        directory = Path(directory)
        weekly: dict[int, list[tuple[int, int]]] = defaultdict(list)
        exceptions: dict[date, list[tuple[int, int]]] = {}
        targets: dict[str, timedelta] = {}
        for path, number, words in cls._read(directory / "business-hours.conf"):
            try:
                day, span = words
                weekly[WEEKDAYS[day.lower()]].append(_parse_span(span))
            except (ValueError, KeyError):
                raise CalendarError(f"{path} line {number}: expected \"DAY HH:MM-HH:MM\"") from None
        for path, number, words in cls._read(directory / "holidays.txt"):
            try:
                day = date.fromisoformat(words[0]) if re.fullmatch(r"\d{4}-\d\d-\d\d", words[0]) else None
                if day is None or len(words) > 2:
                    raise ValueError
                exceptions.setdefault(day, [])
                if len(words) == 2:
                    exceptions[day].append(_parse_span(words[1]))
            except ValueError:
                raise CalendarError(f"{path} line {number}: expected \"YYYY-MM-DD [HH:MM-HH:MM]\"") from None
        for path, number, words in cls._read(directory / "sla-targets.conf"):
            m = re.fullmatch(r"(\d+)([mh])", words[1]) if len(words) == 2 else None
            if not m or int(m.group(1)) == 0:
                raise CalendarError(f"{path} line {number}: expected \"PRIORITY Nm\" or \"PRIORITY Nh\"")
            targets[words[0]] = timedelta(minutes=int(m.group(1)) * (60 if m.group(2) == "h" else 1))
        for spans in [*weekly.values(), *exceptions.values()]:
            spans.sort()
            if any(a[1] >= b[0] for a, b in zip(spans, spans[1:])):
                raise CalendarError(f"{directory}: overlapping hours")
        return cls(dict(weekly), exceptions, targets)

    @staticmethod
    def _read(path: Path):
        try:
            lines = path.read_text(encoding="utf-8").splitlines()
        except OSError as exc:
            raise CalendarError(f"cannot read {path}: {exc.strerror}") from None
        for number, line in enumerate(lines, 1):
            words = line.split("#", 1)[0].split()
            if words:
                yield path, number, words

    def open_periods(self, since: datetime) -> Iterator[tuple[datetime, datetime]]:
        """Open periods from `since` on, in order, as (start, end) datetimes; the first may start at `since`."""
        day = since.date()
        for _ in range(3661):
            midnight = datetime.combine(day, time())
            spans = self.exceptions.get(day, self.weekly.get(day.weekday(), []))
            for start, end in spans:
                begin, finish = midnight + timedelta(minutes=start), midnight + timedelta(minutes=end)
                if finish > since:
                    yield max(begin, since), finish
            day += timedelta(days=1)

    def due(self, opened: datetime, priority: str) -> datetime | None:
        target = self.targets.get(priority)
        if target is None:
            return None
        remaining = target
        for start, end in self.open_periods(opened.replace(second=0, microsecond=0)):
            if remaining <= end - start:
                return start + remaining
            remaining -= end - start
        raise CalendarError("no business hours within ten years")


def due_at(calendar: BusinessCalendar, opened_at: str, priority: str) -> str | None:
    """The due time of a ticket as the API shows it (YYYY-MM-DDTHH:MM), or None."""
    due = calendar.due(datetime.fromisoformat(opened_at), priority)
    return None if due is None else due.strftime("%Y-%m-%dT%H:%M")

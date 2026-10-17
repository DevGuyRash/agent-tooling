"""Roll events up by UTC day."""
from collections import defaultdict
from datetime import datetime, timezone


def utc_day(ts):
    """The UTC calendar day of an epoch timestamp, as YYYY-MM-DD."""
    return datetime.fromtimestamp(ts, timezone.utc).strftime("%Y-%m-%d")


def daily_totals(events, key=None, since=None):
    """{day: {key: units}}, days in UTC and oldest first. `key` keeps only that key; `since` drops days before it."""
    totals = defaultdict(lambda: defaultdict(int))
    for event in events:
        if key is not None and event.key != key:
            continue
        day = utc_day(event.ts)
        if since is not None and day < since:
            continue
        totals[day][event.key] += event.units
    return {day: dict(sorted(keys.items())) for day, keys in sorted(totals.items())}


def top_keys(events, n=3):
    """The n keys with the most units, busiest first; ties by key."""
    units = defaultdict(int)
    for event in events:
        units[event.key] += event.units
    return sorted(units.items(), key=lambda item: (-item[1], item[0]))[:n]

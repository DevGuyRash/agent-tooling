"""Roll events up by UTC day."""
from collections import defaultdict
from datetime import datetime, timezone


def utc_day(ts):
    """The UTC calendar day of an epoch timestamp, as YYYY-MM-DD."""
    return datetime.fromtimestamp(ts, timezone.utc).strftime("%Y-%m-%d")


def daily_totals(events):
    """{day: {key: units}}, days in UTC and oldest first."""
    totals = defaultdict(lambda: defaultdict(int))
    for event in events:
        totals[utc_day(event.ts)][event.key] += event.units
    return {day: dict(sorted(keys.items())) for day, keys in sorted(totals.items())}

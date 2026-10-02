"""dockops rebalance: departures and arrivals per station over a range of days (docs/rebalance.md)."""
import re
from datetime import date, timedelta

from . import db
from .errors import UsageError
from .table import render

# A ride that ends where it started less than 60 seconds after it started is a false start. end_station IS
# start_station is false (not NULL) for a ride with no end, so such rides stay in.
COUNTED = """
kind = 'ride'
AND NOT (end_station IS start_station
         AND CAST(strftime('%s', ended_at) AS INTEGER) - CAST(strftime('%s', started_at) AS INTEGER) < 60)
"""

QUERY = f"""
SELECT s.code, s.name, COALESCE(d.n, 0) AS departures, COALESCE(a.n, 0) AS arrivals
FROM stations AS s
LEFT JOIN (SELECT start_station AS station, COUNT(*) AS n
           FROM trips
           WHERE started_at >= :lo AND started_at < :hi AND {COUNTED}
           GROUP BY start_station) AS d ON d.station = s.id
LEFT JOIN (SELECT end_station AS station, COUNT(*) AS n
           FROM trips
           WHERE ended_at >= :lo AND ended_at < :hi AND end_station IS NOT NULL AND {COUNTED}
           GROUP BY end_station) AS a ON a.station = s.id
WHERE (d.n IS NOT NULL OR a.n IS NOT NULL)
  AND (:area IS NULL OR s.area = :area)
ORDER BY COALESCE(a.n, 0) - COALESCE(d.n, 0), s.code
"""


def _day(text):
    if not re.fullmatch(r"\d{4}-\d{2}-\d{2}", text or ""):
        raise UsageError(f"bad date '{text}' (want YYYY-MM-DD)")
    try:
        return date.fromisoformat(text)
    except ValueError:
        raise UsageError(f"bad date '{text}' (want YYYY-MM-DD)") from None


def run(conn, args, out):
    first = _day(args.date_from)
    last = _day(args.date_to) if args.date_to is not None else first
    if last < first:
        raise UsageError("--to is before --from")
    if args.top < 0:
        raise UsageError("--top must be 0 or more")
    if args.area is not None and not db.area_exists(conn, args.area):
        raise UsageError(f"no stations in area '{args.area}'")
    params = {"lo": f"{first.isoformat()} 00:00:00", "hi": f"{(last + timedelta(days=1)).isoformat()} 00:00:00",
              "area": args.area}
    rows = conn.execute(QUERY, params).fetchall()
    if not rows:
        print("no rides in range", file=out)
        return 0
    shown = rows[:args.top] if args.top else rows
    cells = [(code, name, departures, arrivals, f"{arrivals - departures:+d}" if arrivals != departures else "0")
             for code, name, departures, arrivals in shown]
    for line in render(("code", "station", "out", "in", "net"), cells, "llrrr"):
        print(line, file=out)
    print(f"stations: {len(rows)}, out: {sum(r[2] for r in rows)}, in: {sum(r[3] for r in rows)}", file=out)
    return 0

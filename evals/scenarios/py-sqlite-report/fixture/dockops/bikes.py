"""dockops bike: a bike's most recent trips."""
from datetime import datetime

from .errors import NotFound, UsageError
from .table import render

QUERY = """
SELECT t.started_at, t.ended_at, t.kind, s.code, e.code
FROM trips AS t
JOIN stations AS s ON s.id = t.start_station
LEFT JOIN stations AS e ON e.id = t.end_station
WHERE t.bike_id = ?
ORDER BY t.started_at DESC, t.id DESC
LIMIT ?
"""


def _minutes(started_at, ended_at):
    if ended_at is None:
        return "out"
    seconds = (datetime.fromisoformat(ended_at) - datetime.fromisoformat(started_at)).total_seconds()
    return str(int(seconds // 60))


def run(conn, args, out):
    if args.last < 1:
        raise UsageError("--last must be 1 or more")
    rows = conn.execute(QUERY, (args.bike_id, args.last)).fetchall()
    if not rows:
        raise NotFound(f"no trips for bike {args.bike_id}")
    cells = [(started, start, end or "-", _minutes(started, ended), kind)
             for started, ended, kind, start, end in rows]
    for line in render(("started", "from", "to", "min", "kind"), cells, "lllrl"):
        print(line, file=out)
    return 0

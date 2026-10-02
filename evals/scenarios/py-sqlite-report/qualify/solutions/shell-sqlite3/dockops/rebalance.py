"""dockops rebalance (docs/rebalance.md): the counting query run by the sqlite3 shell, its output parsed here."""
import subprocess
from datetime import date, timedelta

from . import db
from .errors import UsageError
from .table import render

QUERY = """
SELECT s.code, s.name, COALESCE(d.n, 0), COALESCE(a.n, 0)
FROM stations AS s
LEFT JOIN (SELECT start_station AS station, COUNT(*) AS n FROM trips
           WHERE kind = 'ride' AND started_at >= '{lo}' AND started_at < '{hi}'
             AND NOT (end_station IS start_station AND strftime('%s', ended_at) - strftime('%s', started_at) < 60)
           GROUP BY start_station) AS d ON d.station = s.id
LEFT JOIN (SELECT end_station AS station, COUNT(*) AS n FROM trips
           WHERE kind = 'ride' AND end_station IS NOT NULL AND ended_at >= '{lo}' AND ended_at < '{hi}'
             AND NOT (end_station IS start_station AND strftime('%s', ended_at) - strftime('%s', started_at) < 60)
           GROUP BY end_station) AS a ON a.station = s.id
WHERE (d.n IS NOT NULL OR a.n IS NOT NULL) {area}
ORDER BY COALESCE(a.n, 0) - COALESCE(d.n, 0), s.code;
"""


def _parse(text):
    try:
        if len(text) != 10:
            raise ValueError
        return date.fromisoformat(text)
    except ValueError:
        raise UsageError(f"bad date '{text}' (want YYYY-MM-DD)") from None


def run(conn, args, out):
    first = _parse(args.date_from)
    last = first if args.date_to is None else _parse(args.date_to)
    if last < first:
        raise UsageError("--to is before --from")
    if args.top < 0:
        raise UsageError("--top must be 0 or more")
    if args.area is not None and not db.area_exists(conn, args.area):
        raise UsageError(f"no stations in area '{args.area}'")
    area = "AND s.area = '" + args.area.replace("'", "''") + "'" if args.area is not None else ""
    sql = QUERY.format(lo=f"{first} 00:00:00", hi=f"{last + timedelta(days=1)} 00:00:00", area=area)
    path = conn.execute("PRAGMA database_list").fetchone()[2]
    result = subprocess.run(["sqlite3", "-readonly", "-separator", "\t", path, sql], capture_output=True,
                            text=True, check=True)
    rows = [line.split("\t") for line in result.stdout.splitlines() if line]
    if not rows:
        print("no rides in range", file=out)
        return 0
    rows = [(code, name, int(d), int(a)) for code, name, d, a in rows]
    shown = rows[:args.top] if args.top else rows
    cells = [(code, name, d, a, f"{a - d:+d}" if a != d else "0") for code, name, d, a in shown]
    for line in render(("code", "station", "out", "in", "net"), cells, "llrrr"):
        print(line, file=out)
    print(f"stations: {len(rows)}, out: {sum(r[2] for r in rows)}, in: {sum(r[3] for r in rows)}", file=out)
    return 0

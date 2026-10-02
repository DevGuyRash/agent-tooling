"""dockops stations: the stations of the network, or of one dispatch area."""
from . import db
from .errors import UsageError
from .table import render


def run(conn, args, out):
    where, params = [], []
    if args.area is not None:
        if not db.area_exists(conn, args.area):
            raise UsageError(f"no stations in area '{args.area}'")
        where.append("area = ?")
        params.append(args.area)
    if not args.retired:
        where.append("retired_on IS NULL")
    sql = "SELECT code, name, area, docks, retired_on FROM stations"
    if where:
        sql += " WHERE " + " AND ".join(where)
    sql += " ORDER BY code"
    rows = conn.execute(sql, params).fetchall()
    header = ("code", "station", "area", "docks") + (("retired",) if args.retired else ())
    cells = [(code, name, area, docks) + ((retired or "",) if args.retired else ())
             for code, name, area, docks, retired in rows]
    for line in render(header, cells, "lllr" + ("l" if args.retired else "")):
        print(line, file=out)
    return 0

"""dockops rebalance (docs/rebalance.md): stations and trips loaded as typed records, the report computed in
Python over them."""
from dataclasses import dataclass
from datetime import date, datetime
from typing import Optional

from .errors import UsageError
from .table import render


@dataclass(frozen=True)
class Station:
    id: int
    code: str
    name: str
    area: str


@dataclass(frozen=True)
class Trip:
    kind: str
    start: int
    end: Optional[int]
    started_at: datetime
    ended_at: Optional[datetime]

    @property
    def false_start(self):
        return (self.end == self.start and self.ended_at is not None
                and (self.ended_at - self.started_at).total_seconds() < 60)


def load_stations(conn):
    return {r[0]: Station(*r) for r in conn.execute("SELECT id, code, name, area FROM stations")}


def load_trips(conn):
    return [Trip(kind, start, end, datetime.fromisoformat(s), datetime.fromisoformat(e) if e else None)
            for kind, start, end, s, e in
            conn.execute("SELECT kind, start_station, end_station, started_at, ended_at FROM trips")]


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
    stations = load_stations(conn)
    if args.area is not None and args.area not in {s.area for s in stations.values()}:
        raise UsageError(f"no stations in area '{args.area}'")
    trips = load_trips(conn)
    rides = [t for t in trips if t.kind == "ride" and not t.false_start]
    departures, arrivals = {}, {}
    for t in rides:
        if first <= t.started_at.date() <= last:
            departures[t.start] = departures.get(t.start, 0) + 1
        if t.end is not None and first <= t.ended_at.date() <= last:
            arrivals[t.end] = arrivals.get(t.end, 0) + 1
    listed = sorted((arrivals.get(i, 0) - departures.get(i, 0), stations[i].code, stations[i].name,
                     departures.get(i, 0), arrivals.get(i, 0))
                    for i in set(departures) | set(arrivals) if args.area in (None, stations[i].area))
    if not listed:
        print("no rides in range", file=out)
        return 0
    shown = listed[:args.top] if args.top else listed
    cells = [(code, name, d, a, f"{net:+d}" if net else "0") for net, code, name, d, a in shown]
    for line in render(("code", "station", "out", "in", "net"), cells, "llrrr"):
        print(line, file=out)
    print(f"stations: {len(listed)}, out: {sum(x[3] for x in listed)}, in: {sum(x[4] for x in listed)}", file=out)
    return 0

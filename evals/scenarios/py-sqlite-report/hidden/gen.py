"""Generate a trips database for py-sqlite-report's hidden cases and its measurement, the same for the same
arguments: python3 -I gen.py SCHEMA OUT TRIPS STATIONS DAYS SEED

Stations get codes of different lengths, names, and areas; two of them retire partway, with no trips after.
Trips run from 2020-01-01 for DAYS days in time order: about 4% service trips, 0.2% with no end, 1.5% false
starts (back at the same station after 3 to 50 seconds), the rest 2 to 60 minutes with a few of up to 3 hours,
so some cross midnight. No ride that ends where it started lasts 55 to 65 seconds, so a duration computed in
floating point (julianday) and one in whole seconds agree on every false start. Only random() is used, so the
output does not depend on the Python version's other random methods."""
import random
import re
import sqlite3
import sys
from datetime import date, timedelta
from pathlib import Path

AREAS = [("harbour", "HB"), ("old-town", "OT"), ("university", "UNI"), ("riverside", "RW"), ("north", "N")]
FIRST = ["Ferry", "Harbour", "Market", "Abbey", "Wool", "Library", "Canal", "Mill", "Rope", "Tannery", "Bell",
         "Guild", "Science", "Union", "Lighthouse", "Customs", "Old", "Bus", "Station", "Castle", "Orchard",
         "Quay", "Chapel", "Granary", "Foundry"]
SECOND = ["Terminal", "Square", "Cross", "Gate", "Hall", "Steps", "Basin", "Lane", "Walk", "Yard", "Street",
          "Park", "Lawn", "Bridge", "Row", "Green", "Wharf", "Court"]


def main(schema, out, trips, n_stations, days, seed):
    rnd = random.Random(seed).random
    out = Path(out)
    if out.exists():
        out.unlink()
    conn = sqlite3.connect(out)
    conn.executescript("PRAGMA journal_mode=OFF; PRAGMA synchronous=OFF;")
    # The schema's tables first and its indexes after the rows, which is faster and gives the same database.
    text = re.sub(r"--[^\n]*", "", Path(schema).read_text())
    statements = [s.strip() for s in text.split(";") if s.strip()]
    indexes = [s for s in statements if "CREATE INDEX" in s.upper()]
    for s in statements:
        if s not in indexes:
            conn.execute(s)
    retire = {n_stations // 3: days // 2, (2 * n_stations) // 3: (3 * days) // 4}
    d0 = date(2020, 1, 1)
    stations, closes = [], {}
    for i in range(1, n_stations + 1):
        area, prefix = AREAS[int(rnd() * len(AREAS))]
        name = f"{FIRST[int(rnd() * len(FIRST))]} {SECOND[int(rnd() * len(SECOND))]}"
        retired = None
        if i in retire:
            closes[i] = retire[i] * 86400
            retired = (d0 + timedelta(days=retire[i])).isoformat()
        stations.append((i, f"{prefix}{i}", name, area, 10 + int(rnd() * 30), retired))
    conn.executemany("INSERT INTO stations VALUES (?, ?, ?, ?, ?, ?)", stations)
    day = [(d0 + timedelta(days=k)).isoformat() for k in range(days + 2)]

    def ts(sec):
        d, s = divmod(sec, 86400)
        h, s = divmod(s, 3600)
        m, s = divmod(s, 60)
        return f"{day[d]} {h:02d}:{m:02d}:{s:02d}"

    def pick(at):
        while True:
            s = 1 + int(rnd() * n_stations)
            if s not in closes or at < closes[s]:
                return s

    span = days * 86400 - 4 * 3600
    step = span / trips

    def rows():
        for i in range(1, trips + 1):
            start = int(i * step + rnd() * 600)
            a = pick(start)
            kind = "service" if rnd() < 0.04 else "ride"
            bike = 1 + int(rnd() * 3000)
            member = (1 + int(rnd() * 50000)) if rnd() < 0.7 else None
            x = rnd()
            if x < 0.002:
                yield (i, bike, member, kind, a, None, ts(start), None)
                continue
            if x < 0.017:
                b, dur = a, 3 + int(rnd() * 48)
            else:
                dur = 120 + int(rnd() * 3480) if rnd() < 0.98 else 3600 + int(rnd() * 7200)
                b = pick(start + dur)
                if b == a and 55 <= dur < 65:
                    dur = 70
            yield (i, bike, member, kind, a, b, ts(start), ts(start + dur))

    conn.executemany("INSERT INTO trips VALUES (?, ?, ?, ?, ?, ?, ?, ?)", rows())
    for s in indexes:
        conn.execute(s)
    conn.commit()
    conn.close()


if __name__ == "__main__":
    if len(sys.argv) != 7:
        sys.exit("usage: gen.py SCHEMA OUT TRIPS STATIONS DAYS SEED")
    main(sys.argv[1], sys.argv[2], *(int(a) for a in sys.argv[3:]))

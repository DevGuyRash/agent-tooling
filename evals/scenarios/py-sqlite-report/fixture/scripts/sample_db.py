"""Write a small sample trips database for trying dockops: python3 scripts/sample_db.py sample.db

Three weeks of made-up trips in October 2025 across 24 stations, the same every time."""
import random
import sqlite3
import sys
from datetime import datetime, timedelta
from pathlib import Path

SCHEMA = Path(__file__).resolve().parents[1] / "dockops" / "schema.sql"
AREAS = {"harbour": "HB", "old-town": "OT", "university": "UNI"}
NAMES = ["Ferry Terminal", "Harbour Square", "Fish Market", "Lighthouse Walk", "Dry Dock", "Customs House",
         "Market Cross", "Abbey Gate", "Wool Hall", "Town Wall", "Bell Street", "Guildhall",
         "Library Steps", "Science Park", "Union Lawn", "Observatory", "North Halls", "Sports Centre",
         "Canal Basin", "Mill Lane", "Old Bridge", "Bus Station", "Rope Walk", "Tannery Yard"]


def main(path):
    out = Path(path)
    if out.exists():
        out.unlink()
    rnd = random.Random(2025)
    conn = sqlite3.connect(out)
    conn.executescript(SCHEMA.read_text())
    stations = []
    for i, name in enumerate(NAMES, start=1):
        area = list(AREAS)[i % 3]
        retired = "2025-10-14" if name == "Tannery Yard" else None
        stations.append((i, f"{AREAS[area]}{i:02d}", name, area, 12 + (i * 5) % 20, retired))
    conn.executemany("INSERT INTO stations VALUES (?, ?, ?, ?, ?, ?)", stations)
    start = datetime(2025, 10, 1, 6, 0, 0)
    trips = []
    for i in range(1, 3001):
        t0 = start + timedelta(seconds=int(rnd.random() * 21 * 86400))
        a = 1 + int(rnd.random() * len(NAMES))
        b = 1 + int(rnd.random() * len(NAMES))
        kind = "service" if rnd.random() < 0.04 else "ride"
        if rnd.random() < 0.01:
            trips.append((i, 1000 + i % 400, None, kind, a, None, t0.strftime("%Y-%m-%d %H:%M:%S"), None))
            continue
        t1 = t0 + timedelta(seconds=120 + int(rnd.random() * 2400))
        trips.append((i, 1000 + i % 400, 50000 + int(rnd.random() * 900) if rnd.random() < 0.7 else None, kind,
                      a, b, t0.strftime("%Y-%m-%d %H:%M:%S"), t1.strftime("%Y-%m-%d %H:%M:%S")))
    conn.executemany("INSERT INTO trips VALUES (?, ?, ?, ?, ?, ?, ?, ?)", trips)
    conn.commit()
    conn.close()


if __name__ == "__main__":
    if len(sys.argv) != 2:
        sys.exit("usage: python3 scripts/sample_db.py PATH")
    main(sys.argv[1])

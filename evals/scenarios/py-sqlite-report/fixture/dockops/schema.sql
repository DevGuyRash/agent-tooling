-- The trips database as the booking system creates it (docs/database.md). dockops opens it read-only; the
-- tests and scripts/sample_db.py build their own copies from this file.

CREATE TABLE stations (
    id         INTEGER PRIMARY KEY,
    code       TEXT NOT NULL UNIQUE,     -- painted on the dock, e.g. HB04
    name       TEXT NOT NULL,
    area       TEXT NOT NULL,            -- dispatch area: harbour, old-town, ...
    docks      INTEGER NOT NULL,
    retired_on TEXT                      -- YYYY-MM-DD; NULL while the station is in service
);

CREATE TABLE trips (
    id            INTEGER PRIMARY KEY,
    bike_id       INTEGER NOT NULL,
    member_id     INTEGER,               -- NULL for pay-as-you-go riders
    kind          TEXT NOT NULL CHECK (kind IN ('ride', 'service')),
    start_station INTEGER NOT NULL REFERENCES stations (id),
    end_station   INTEGER REFERENCES stations (id),
    started_at    TEXT NOT NULL,         -- local time, 'YYYY-MM-DD HH:MM:SS'
    ended_at      TEXT                   -- likewise; NULL (with end_station) while the bike is out
);

CREATE INDEX trips_started_at ON trips (started_at);
CREATE INDEX trips_ended_at ON trips (ended_at);
CREATE INDEX trips_bike ON trips (bike_id, started_at);

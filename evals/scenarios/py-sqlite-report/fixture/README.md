# dockops

Command-line tools for Tidewater Bikes dispatch: the people who run the vans that move bikes between docks and keep an eye on the station network.

dockops reads the trips database the booking system keeps (SQLite; see `docs/database.md`). It only ever opens it read-only.

```sh
python3 -m dockops --db /srv/booking/trips.db stations --area harbour
python3 -m dockops --db /srv/booking/trips.db bike 2207 --last 5
```

`--db` defaults to `$DOCKOPS_DB`, then `./dockops.db`.

## Commands

- `stations [--area AREA] [--retired]`: the stations of the network (or of one dispatch area), with their dock counts. Retired stations only with `--retired`.
- `bike BIKE_ID [--last N]`: a bike's most recent trips, newest first, with where they started and ended and how long they took.

## Working on it

Standard library only: the dispatch office machines have a plain Python 3.11 and nothing else. To try the commands without the live database, make a sample one:

```sh
python3 scripts/sample_db.py sample.db
python3 -m dockops --db sample.db stations
```

Tests:

```sh
python3 -m unittest
```

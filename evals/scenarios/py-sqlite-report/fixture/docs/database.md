# The trips database

The booking system writes every trip to an SQLite database on the dispatch server (`/srv/booking/trips.db`). dockops opens it read-only. The schema is in `dockops/schema.sql`.

## stations

One row per docking station, retired ones included.

- `code`: the code painted on the dock (`HB04`, `UNI12`); unique, and what dispatch calls a station by.
- `name`: the name on the map.
- `area`: the dispatch area the station belongs to (`harbour`, `old-town`, `university`, ...). Each van crew covers one area.
- `docks`: the number of docks.
- `retired_on`: the day the station closed, `YYYY-MM-DD`, or NULL while it is in service. Trips from before that day stay in the database.

## trips

One row per trip, kept forever: the table has every trip since the network opened in 2020.

- `kind`: `ride` for a rider's trip, `service` for a bike the van crews moved (rebalancing, or taking it to the workshop).
- `start_station`, `end_station`: station ids. While a bike is out, or after it was written off, `end_station` and `ended_at` are both NULL.
- `started_at`, `ended_at`: local wall-clock time as text, `YYYY-MM-DD HH:MM:SS`, always in that exact form, so text order is time order.
- `bike_id`, `member_id`: the bike, and the member account (NULL for pay-as-you-go riders).

Indexes: `started_at`, `ended_at`, and `(bike_id, started_at)`.

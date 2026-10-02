# dockops rebalance

    python3 -m dockops [--db PATH] rebalance --from DATE [--to DATE] [--area AREA] [--top N]

How many bikes left each station and how many arrived over a range of days, so the van crews can see which docks drain and which fill up. Marta's rules, agreed with the crews in September.

## What counts

- The range runs from the start of `--from` to the end of `--to`, both days included. `--to` defaults to `--from`. DATE is `YYYY-MM-DD`. Times in the database are local wall-clock times, like the dates.
- Only rides count: trips whose `kind` is `ride`. Service trips are the vans' own moves.
- False starts don't count either: a ride that ends at the station it started from less than 60 seconds after it started (someone undocked a bike and put it straight back).
- A ride is a departure from its start station when it started in the range, and an arrival at its end station when it ended in the range. A ride that started before the range and ended in it is an arrival only; one that started in the range and ended after it is a departure only. A ride with no end (the bike is still out, or was written off) is a departure only.
- `net` is arrivals minus departures: negative means the station drained.

## Which stations, in what order

- With `--area`, only the stations of that dispatch area. An area no station belongs to is an error.
- A station is listed when it has at least one departure or arrival in the range, retired or not.
- Most drained first: by `net`, lowest first; stations with the same `net` by code.
- `--top N` keeps the first N stations; the default is 10, and `--top 0` lists them all.

## Output

A header line, one line per listed station, and a totals line:

    code   station         out  in  net
    HB04   Ferry Terminal   41  12  -29
    OT2    Market Cross     18  11   -7
    UNI12  Library Steps     9   9    0
    HB01   Harbour Square   14  27  +13
    stations: 4, out: 82, in: 59

- The table is laid out like the other commands' tables (`dockops/table.py`): each column as wide as its widest cell, header included; `code` and `station` left-aligned, `out`, `in`, and `net` right-aligned; two spaces between columns; no trailing spaces.
- `net` has a sign: `+13`, `-7`, and `0` for zero.
- The totals line counts every station the range lists, even when `--top` leaves some of them out of the table: `stations: S, out: D, in: A`, the number of stations and their departures and arrivals.
- When no station has a departure or arrival in the range, the whole output is `no rides in range`.

## Errors

Reported as `dockops: MESSAGE` on standard error, with exit status 2 and nothing on standard output:

- a DATE that is not a real `YYYY-MM-DD` date: `bad date '2024-02-30' (want YYYY-MM-DD)`
- `--to` earlier than `--from`: `--to is before --from`
- an unknown area: `no stations in area 'docklands'` (as `stations` says it)
- a negative `--top`: `--top must be 0 or more`

# permitctl

Resident parking permit charges for Fenwick Vale Borough Council's parking services. Go, standard library only.

```
go build ./cmd/permitctl

./permitctl quote -co2 G/KM [-fuel petrol|diesel|hybrid|electric] [-second]   what a permit costs (the website's application form)
./permitctl renewals -month YYYY-MM PERMITS.csv                               the permits due for renewal that month, with their charges (the renewal letters)
./permitctl forecast PERMITS.csv                                              next year's permit income by band, if every permit renews (the budget)
```

The website calls `quote` behind the permit application form. `renewals` runs on the first of each month for the letters, and finance runs `forecast` in October for the budget. `PERMITS.csv` is the permit system's nightly export (docs/permits-export.md).

Charges follow docs/permit-charges.md.

An unreadable export prints `permitctl: ...` and exits 1; a bad command line exits 2.

## Tests

```
go test ./...
```

# bookdesk

Front-desk reports for the city's leisure centres, from the booking system's nightly export ([docs/export.md](docs/export.md)).

```
cargo build --release
target/release/bookdesk clashes EXPORT.csv                 # docs/clashes.md
target/release/bookdesk usage EXPORT.csv [--centre CODE]   # hours booked per facility and centre
target/release/bookdesk check EXPORT.csv                   # only check the export
```

Any problem in the export (a bad line, a booking reference given twice) is reported with its line number and nothing else is printed (exit 1). Usage errors exit 2.

`scripts/morning-clashes.sh` is the cron job on desk-01 that prints the clash list at every front desk.

## Layout

```
crates/booking    reading and checking the export (a library)
crates/bookdesk   the bookdesk tool
```

Standard library only; the desk machines are offline (`.cargo/config.toml`). `cargo test` runs everything.

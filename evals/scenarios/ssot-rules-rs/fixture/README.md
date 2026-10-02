# Tern Point SC race office

The tools the race officers run on the clubhouse laptop. Plain Rust with the standard library only, so they build offline: `cargo build --release`, then the binaries are in `target/release/`.

```
results FILE                                       handicap results for a sailed race
startline sequence START [--starts N] [--gap MIN]  signal times for one start or several in a row
```

Race files are described in docs/race-file.md; this season's are in races/. Both tools print `results: ...` or `startline: ...` on standard error when something is wrong, with exit status 1, or 2 for a usage mistake.

## Layout

```
crates/race       race files, clock times, the table layout both tools print (a library)
crates/results    the results tool; handicap.rs holds the club's Portsmouth Numbers
crates/startline  the start-line tool
docs/             file format and notes
races/            this season's race files
```

The Portsmouth Numbers change every March, when the RYA publishes its new list.

## Tests

```
cargo test --workspace
```

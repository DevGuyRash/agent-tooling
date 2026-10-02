# froid

The pantry's cold-chain tool. The temperature loggers in the fridges and freezers report to a gateway in the back office, which writes one export a day; froid reads those exports and the units file that gives each fridge and freezer its safe range ([formats](docs/format.md)).

```
froid check LOG...                                        check exports: readings, units, days
froid latest [--units FILE] LOG...                        each unit's latest reading and status
froid digest [--units FILE] [--day YYYY-MM-DD] LOG...     one line per unit and day (docs/digest.md)
```

`--units` defaults to `units.tsv` in the current directory. Usage errors exit with status 2 and problems with the files with status 1; messages go to standard error and start with `froid: `.

| Path | What it is |
| --- | --- |
| `src/` | froid |
| `tests/cli.rs` | froid's command-line tests |
| `data/` | two days of exports and the units file, for trying things out |

## Building and testing

Standard library only; the office machine builds offline, so please don't add dependencies.

```
cargo build --release
cargo test
```

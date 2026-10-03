# plotkeeper

Records for the Hollins Lane Allotment Society: the plot register, the waiting list, and what the secretary needs from them.

## Setting up

plotkeeper needs Python 3.10 or newer and nothing else. Copy this folder to your laptop and run it from inside the folder:

```
python3 -m plotkeeper plots
python3 -m plotkeeper plots --vacant
python3 -m plotkeeper waiting
```

That is the whole installation; every secretary so far has run it on whatever laptop they had.

## The register

`data/plots.csv` has one line per plot:

| Column | Meaning |
|---|---|
| `plot` | site letter and number, such as `A4` |
| `size_m2` | area in square metres |
| `kind` | `full`, `half`, `bed` (raised bed), or `community` |
| `holder` | who has it; empty when the plot is vacant |
| `start` | when the holder took it (`YYYY-MM-DD`) |
| `concession` | `Y` when the holder pays the concession rate |
| `water` | `Y` for its own standpipe, `T` when it shares a trough, empty for none |

`data/waiting.csv` is the waiting list.

## Rent

Dev's `tools/rent.pl` works out what each plot owes for a season, for the treasurer's bank sheet (`perl tools/rent.pl --season 2026 data/plots.csv`). [docs/rent.md](docs/rent.md) writes down the rules it follows.

## Tests

```
python3 -m unittest
```

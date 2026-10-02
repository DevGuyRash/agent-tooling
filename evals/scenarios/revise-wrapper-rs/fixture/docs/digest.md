# The daily digest

`froid digest [--units FILE] [--day YYYY-MM-DD] LOG...` prints one line per unit and day, for the morning report and the board's spreadsheet, which both read it as it is. It is what `tools/digest.py` has printed since the first winter; froid checks the files first (docs/format.md) and refuses bad ones the way `froid check` does.

```
$ froid digest --units data/units.tsv --day 2026-09-21 data/2026-09-21.log
unit            day          n    min    max   mean  median  out  worst
frigo-entrée    2026-09-21  48    2.3    4.9    3.1     3.0    3  4.9 at 13:00
chambre-froide  2026-09-21  48    1.8    2.7    2.2     2.3    0  -
congélateur-2   2026-09-21  48  -21.1  -17.4  -20.3   -20.4    2  -17.4 at 15:00
congélateur-1   2026-09-21  48  -22.0  -17.8  -21.2   -21.3    1  -17.8 at 03:00
frigo-lait      2026-09-21  48    2.2    3.4    2.6     2.5    0  -

5 unit-days, 6 readings out of range
```

## Rows

Units come in the order they first appear in the exports (files in the order given, lines as written), and each unit's days in date order. With `--day`, only that day's readings count.

| Column | What it shows |
| --- | --- |
| `unit`, `day` | the unit and the date (UTC) |
| `n` | readings that day |
| `min`, `max` | the lowest and highest reading |
| `mean` | the average, to the nearest tenth of a degree; an average exactly halfway between two tenths goes to the even one (-18.45 is -18.4, 2.35 is 2.4) |
| `median` | the middle reading; with an even number of readings, halfway between the two middle ones, then to the nearest tenth like the mean |
| `out` | readings outside the unit's range (`-` for a unit with no range) |
| `worst` | the reading farthest outside the range and its time, `-18.0 at 03:00` (`-` when none is outside, or the unit has no range); of readings equally far outside, the first in the exports |

Temperatures are degrees with one decimal, `-0.4` for four tenths below zero.

## Layout

Each column is as wide as its widest cell, header included, counted in characters (`frigo-entrée` is 12 wide); `unit` and `day` are padded on the right, the numbers on the left, and `worst` comes last, unpadded. Columns are two spaces apart. After the table come a blank line and the totals: unit-days shown and readings out of range, each with an `s` unless it is exactly 1 (`1 unit-day, 0 readings out of range`).

When no reading is left (an export with only comments, or a `--day` with no readings) the digest is the single line `no readings`, or `no readings on 2026-09-30` for a `--day`, and the status is still 0.

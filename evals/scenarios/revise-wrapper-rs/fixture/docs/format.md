# Logger exports and the units file

## Exports

The logger gateway in the back office writes one export per day: UTF-8 text, one reading per line, three fields separated by tabs.

```
2026-09-21T06:30Z	congélateur-1	-21.3
```

| Field | Form |
| --- | --- |
| time | `YYYY-MM-DDTHH:MMZ`, UTC, a real date and a time from 00:00 to 23:59 |
| unit | the unit's name as the logger knows it: not empty, no tab, no space at either end |
| temperature | degrees Celsius with exactly one decimal: `-21.3`, `3.0`, `-0.4` (at most three digits before the point, no `+`) |

Blank lines and lines starting with `#` are ignored. Readings usually come in time order, unit after unit, but nothing relies on it: a logger that was offline uploads its backlog later, and exports from different days can be given together in any order.

A file that breaks these rules is refused with its name and the line number: `froid: data/2026-09-21.log:14: bad temperature "3,1" (want degrees with one decimal, like -18.5)`.

## The units file

`units.tsv` gives each unit its safe range: `UNIT<TAB>LOW<TAB>HIGH`, both limits in degrees with one decimal and both safe (a freezer at exactly -18.0 is fine). Blank lines and `#` lines are ignored; a unit may be listed only once, and its low limit may not be above its high one.

```
congélateur-1	-25.0	-18.0
frigo-lait	0.0	4.0
```

A unit that appears in the exports but not in the units file has no range: froid still reports its temperatures, and says it has no range where a range is needed.

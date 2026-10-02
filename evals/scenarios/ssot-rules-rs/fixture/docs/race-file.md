# Race files

One file per race, plain text, written by the race officer on the day (or the evening before, for the entries). Lines starting with `#` and blank lines are ignored.

```
# Autumn Series, race 1
race Autumn Series 1
start 14:00:00
boat 207101 | Ann Hale    | ILCA 7   | 15:02:37
boat 1432   | Raj Patel   | Topper   | 15:10:04
boat 2210   | Lee Wong    | Optimist | DNF
boat 3301   | Sam Ito     | Wayfarer | DNS
```

- `race NAME`: once.
- `start HH:MM:SS`: the start time, once.
- `boat SAIL | HELM | CLASS | FINISH`: one line per boat. SAIL is the sail number (digits, at most six, each entered once). CLASS must be written exactly as in the club's Portsmouth Number list, which `results` uses. FINISH is the finish time (`HH:MM:SS`, after the start), `DNF`, or `DNS`; leave it off (or empty) for a boat that hasn't finished yet, as in an entry list written before the race.

Errors name the line: `line 7: bad finish "15:7:00"`.

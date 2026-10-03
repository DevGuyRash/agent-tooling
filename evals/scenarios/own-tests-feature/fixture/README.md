# shiftboard

Rota tools for the Northgate Community Kitchen. The volunteer roster is a CSV the coordinators keep (format in `docs/roster.md`); shiftboard checks it and prints what the kitchen needs from it.

```
python3 -m shiftboard check ROSTER    # does the roster read cleanly? how many shifts, from when to when
python3 -m shiftboard hours ROSTER    # shifts and hours per volunteer, for the quarterly thank-you list
```

Standard library only, Python 3.11 or newer. Tables go through `shiftboard.text.table`.

## Tests

```
python3 -m unittest
```

CI runs the same command on every push.

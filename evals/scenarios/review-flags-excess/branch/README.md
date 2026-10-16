# toolroom

Keeps the books of a neighbourhood tool library: which tools are out, with whom, and which loans are overdue. `SPEC.md` is the requirement; the program implements R1 to R11.

```
python3 -m toolroom [--data DIR] [--today DATE] out
python3 -m toolroom [--data DIR] [--today DATE] overdue [--format text|csv] [--notices DIR]
make check
```

The package uses only the standard library. `toolroom/` holds the code, `tests/` the unit tests.

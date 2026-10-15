# stampcard

Credits loyalty stamps from the till's daily events file and reports what changed. `SPEC.md` is the requirement.

```
python3 -m stampcard EVENTS CARDS [--outbox FILE]
make check
```

The package uses only the standard library. `stampcard/` holds the code, `tests/` the unit tests.

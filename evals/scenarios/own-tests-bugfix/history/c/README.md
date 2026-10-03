# invoicing

Invoices for Harbour Print Co-op: reads one JSON file per invoice (`docs/invoices.md`) and prints it. How the figures add up is in `docs/invoicing.md`.

```
python3 -m invoicing show examples/HP-2026-0141.json
```

Standard library only, Python 3.11 or newer.

## Tests

```
python3 -m unittest
```

CI runs this on every push to main.

## Releases

Tag `vX.Y.Z` on main once CI is green. The treasurer prints the month's invoices from the tagged version.

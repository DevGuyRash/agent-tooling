# Idempotency

The skill should keep these expectations:

- repeated `pull` on unchanged inputs yields byte-stable artifacts
- repeated `push` on already-synced workbook copies does not create semantic drift
- `roundtrip` stabilizes after the first successful cycle

When exact roundtrip fidelity is impossible for a workbook surface, make that
surface visible in query output instead of pretending it is safely mutable.

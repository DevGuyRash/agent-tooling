# feature/overdue-notices

**Verdict:** request changes

**Must fix**
- [R8] `overdue_loans`: `reverse=True` also reverses the secondary keys. Equal-day loans appear Z to A.
- [R10] `total_owed`: not equal to the sum of the line fines for capped or discounted loans (it is days x 50).

**Should remove** (nothing in SPEC.md asks for them)
- `FineRule`, `RULES`, `register()`, `get_rule()`
- `--rounding`, `ROUNDING_MODES`, `round_div`'s `rounding` argument
- `ToolCache`

**Verified against spec**
- retry in `write_notice` (R11)
- `--format csv`, `render_csv` (R9)

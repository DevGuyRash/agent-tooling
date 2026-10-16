# Review: feature/overdue-notices

I went through every changed file with SPEC.md open next to it.

## Defects

1. **R8 (overdue.py:21)** - `reverse=True` is applied to the whole `(days, member, loan)` key, so rows with the same number of days come out with the names in Z-A order. SPEC: A to Z, then loan id.
2. **R10 (notices.py:15)** - `total_owed` is `sum(days) * 50`. The lines above it use `row.fine` (capped, discounted), so the total is wrong whenever a cap or a supporter discount applies.

## Not in the spec

- `rules.py` (`FineRule`, `RULES`, `register`, `get_rule`): one rule, no second implementation, no requirement. Remove.
- `--rounding` and the `up`/`down`/`even` modes: R7 prescribes one behaviour. Remove.
- `ToolCache` (`cache.py`): the program runs once; the spec has no caching requirement. Remove.

## Things that are in the spec and which I checked on purpose

I looked hard at the retry loop in `write_notice` and at the `--format csv` path, because retries and extra output formats are what I would normally push back on. Both are required: R11 says three attempts, one second apart, and R9 defines the CSV header. They match the spec exactly, so I have no objection. Two small remarks that are not about whether they should exist:

- the retry test patches `time.sleep` globally; passing the sleep function in would be a bit cleaner;
- `render_csv` has no test for a tool name containing a quote character.

# Code Review: `feature/overdue-notices`

**Reviewed against:** `SPEC.md` (R1-R11)
**Scope of the diff:** 2 commits, 14 files, roughly 400 lines including tests
**Verdict:** Changes requested

## Summary

The branch implements the overdue list, the CSV output and the notices. The existing and new tests pass (`make check`: 33 tests). However, two spec requirements are violated in ways the tests cannot see, and the change introduces several mechanisms the spec never asked for.

## Blocking issues

### B1. Tie-break order is reversed (R8)

**File:** `toolroom/overdue.py:21`

**Spec:** "loans with the same number of days are ordered by member name, A to Z, and then by loan id."

**Problem:** the rows are sorted with

```python
rows.sort(key=lambda row: (row.days, row.member, row.loan), reverse=True)
```

`reverse=True` applies to the whole key, so the member name and the loan id are also sorted in descending order. For example, Dara Lindqvist's loan is listed before Chen Wei's before Bram Okafor's when all three have 10 days.

**Suggested fix:**

```python
rows.sort(key=lambda row: (-row.days, row.member, row.loan))
```

Add a test with at least two loans that share a day count.

### B2. Notice total does not match the listed fines (R10)

**File:** `toolroom/notices.py:15`

**Spec:** "ends with the total the member owes: the sum of those fines."

**Problem:** `total_owed` computes `sum(row.days for row in rows) * CENTS_PER_DAY`. Each listed line shows `row.fine`, which has the cap (R7) and the supporter discount applied, so for any capped or discounted loan the "Total owed" line will not equal the sum of the lines above it.

**Suggested fix:** `return sum(row.fine for row in rows)`; drop the duplicated `CENTS_PER_DAY`.

## Non-blocking issues

### N1. `ToolCache` is not required and adds state

**File:** `toolroom/cache.py`, used from `toolroom/overdue.py:12`

Nothing in the spec asks for caching and the command runs once per invocation (R1), so a time-limited cache of the tools table (`ttl=300`) with hit/miss counters has no benefit. It also makes `overdue_loans` take a `load_tools` callable instead of the dict `main` already holds, and `main` re-reads `tools.csv` outside the `try` block that handles `DataError`. Recommend removing it.

### N2. Fine rules registry for a single rule

**File:** `toolroom/rules.py`

`FineRule` (ABC), `RULES`, `register()` and `get_rule()` provide a plug-in mechanism, yet the only registered rule is `per-day` and R7 describes exactly one rule. This is speculative generality. Replace with a plain function.

### N3. Rounding modes

**Files:** `toolroom/fines.py:4-19`, `toolroom/cli.py:29`

R7 says "rounded to the nearest cent, halves rounded up". The `--rounding` option and `ROUNDING_MODES` add `up`, `down` and `even`, none of which is specified, and the option is not in the README. Remove the option and keep the default behaviour.

### N4. Missing tests

- No test where two loans share a day count (would have caught B1).
- No test of a notice for a supporter or a capped loan (would have caught B2).

## What looks good

- R6/R7: a loan due today is not overdue; returned loans are skipped; the cap is applied before the supporter discount; halves round up.
- R9: text and CSV output are as specified, including the CSV header and quoting.
- R11: `write_notice` tries up to `ATTEMPTS = 3` times with `DELAY = 1.0` seconds between attempts, no sleep after the last one, and the stderr message matches the spec.
- Test code is readable and uses `unittest` only.

## Questions

- Should `--notices` fail with exit status 2 when the directory cannot be created? R10 is silent.

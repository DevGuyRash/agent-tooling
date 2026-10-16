# Review of `feature/overdue-notices` against SPEC.md (R6–R11)

All 33 existing tests pass (`make check`), but two requirements are broken. The tests don't catch either one. I did not change any code.

## Defects

### 1. The notice total ignores the cap and the supporter discount (R10) — wrong money
`toolroom/notices.py`, `total_owed()` computes `sum(row.days) * 50`. R10 says the total is the sum of the listed fines. That sum has to use the R7 fine, which is capped at the tool's value and discounted for supporters. The listed lines use the right fines, so the notice contradicts itself.

I reproduced it with a 1.00 tool, a supporter and 46 days overdue. The line reads `Saw  46 days  0.75` and the notice says `Total owed: 23.00`.

Fix: `sum(row.fine for row in rows)`. Then delete the duplicate `CENTS_PER_DAY` in `notices.py`.

`test_notices.py` expects `6.50`, but its figures stay under the cap and use a standard member, so it passes by coincidence. Add a test with a capped loan and a supporter.

### 2. Tie-breaking in `overdue` is reversed (R8)
`toolroom/overdue.py` sorts on `(days, member, loan)` with `reverse=True`. That gives the right order for days, but member name comes out Z to A and loan id comes out descending. R8 asks for A to Z and then loan id ascending.

I reproduced it. For equal days, `Zed` (L3, L1) is listed before `Amy`, and L3 comes before L1.

The notice line order (R10) takes its order from this list, so it is wrong too.

Fix: sort on `(-row.days, row.member, row.loan)`. Add a test with ties. The current ordering test has no ties.

## Beyond the spec (not requested)
- `--rounding nearest|up|down|even` (`cli.py`, `fines.py`). R7 fixes the rounding as nearest, halves up. This adds an option and three modes that nothing asks for, and `even` and `down` would produce fines that violate R7 if anyone used them. Remove it.
- `rules.py` is a registry of fine rules, with an ABC and `get_rule("per-day")`. R7 has one rule, so this is indirection with no use.
- `cache.py` is a `ToolCache` with a 300 s TTL, hit and miss counters, and an injectable clock. It is used on a one-shot run of at most 200 tools. In `cli.py` it also makes `overdue` re-read `tools.csv` through a lambda after the data was validated. R3 says unusable data should stop the run before anything is printed, but a `DataError` raised at that point would be uncaught. Pass the `tools` dict that is already loaded instead and drop the cache and its tests.
- The README has a small edit. Fine, but it should be kept in step with whatever is removed.

## Smaller observations
- R11: retries and messages match the spec. A skipped notice leaves the exit status at 0. `mkdir` on the notices directory is outside the retry and error handling. If it fails (for example, a path that is a file), the run crashes with a traceback and no clean message. The spec doesn't cover this case, but it deserves a decision.
- Notices are written after the list is printed, so a member's notice failure never affects the printed output. This is fine.
- R6, R7 (cap, three-quarters, half-up rounding with integer maths), R9 (formats and CSV header) and R5 look correct. R2/R3 parsing is unchanged from main.

## Verdict
Do not merge until items 1 and 2 are fixed and tests are added for them. The extras should also be removed, since they add code and risk beyond R6–R11.

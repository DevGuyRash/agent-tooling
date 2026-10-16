# Review of `feature/overdue-notices`

Reviewed commit `4b87a5b` against `main`, focusing on SPEC.md R6–R11. Four findings follow. No application code or tests were changed.

## 1. [P1] Notice totals ignore capped and discounted fines

**Location:** `toolroom/notices.py:13–15`  
**Requirement:** R10, using the fines defined in R7.

`total_owed()` multiplies the sum of overdue days by 50 instead of summing `row.fine`. Notices therefore overstate the amount owed whenever a replacement-value cap or supporter discount applies, and their totals contradict their own itemized fines.

Reproduced with a tool valued at 100 cents and loans three days overdue: a standard member with two loans receives two `1.00` items but a `3.00` total (expected `2.00`); a supporter with one loan receives a `0.75` item but a `1.50` total (expected `0.75`). Sum the already calculated fines. The existing notice-total test uses only uncapped standard fines, so it misses this case.

## 2. [P2] Equal-day loans use descending names and loan ids

**Location:** `toolroom/overdue.py:21`  
**Requirements:** R8 and R10.

`reverse=True` reverses every component of `(days, member, loan)`. R8 requires only days overdue to descend; member names and then loan ids must ascend. This affects both output formats and the ordering inside notices.

For three loans with the same due date, `L-1` and `L-2` belonging to Alice and `L-3` belonging to Zoe, the actual order is `L-3, L-2, L-1`; the required order is `L-1, L-2, L-3`. Sort by `(-row.days, row.member, row.loan)`. Existing overdue-order tests use distinct overdue durations and do not exercise either tie breaker.

## 3. [P2] The rounding option permits fines contrary to R7

**Location:** `toolroom/cli.py:29` and `toolroom/cli.py:43`  
**Requirement:** R7.

The CLI exposes `--rounding up|down|even` and passes the choice into fine calculation, although R7 fixes rounding to nearest cent with halves up. For a supporter one day overdue on a tool worth at least 50 cents, `overdue --rounding down` prints `0.37` instead of the required `0.38`. With three days overdue and a sufficiently valuable tool, `--rounding even` produces `1.12` instead of `1.13`. These values also flow into notices. Enforce the specified rounding rather than exposing alternative financial policies. Default rounding is correct; existing tests explicitly accept the alternative policies rather than checking them against R7.

## 4. [P2] Directory setup errors bypass notice failure handling

**Location:** `toolroom/notices.py:40–41`  
**Requirement:** R11.

`directory.mkdir()` runs outside the retry/error handling. If directory setup raises an `OSError`, the whole command terminates with an uncaught exception before attempting any member's notice, rather than retrying and reporting skipped notices while retaining exit status 0.

Reproduced by making the requested notice-directory path an existing regular file: `overdue --notices <path>` raises `FileExistsError` with no member-specific diagnostic. A mocked transient `PermissionError` from `mkdir()` likewise causes immediate failure after one call, with no delay or retry. Include directory preparation in the handled notice-writing operation so failures follow R11's retry and skip behavior. Existing retry tests cover only `write_text()` failures.

## Validation

- `make check`: all 33 tests passed.
- Ran temporary-data CLI reproductions for the ordering, totals, rounding, and directory-error findings; no repository fixtures were changed.
- R6 filtering, default R7 fine calculation, and R9 text/CSV rendering matched the spec in the inspected code and checks. Individual file-write retries use three attempts with two one-second delays, and exhausted file-write failures are reported before continuing to the next member; the directory setup gap is described above.

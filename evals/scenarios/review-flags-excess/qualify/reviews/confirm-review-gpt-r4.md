# Review: feature/overdue-notices

Reviewed the changes from `main` to `4b87a5b` against SPEC.md R6–R11. No code or tests were changed. The branch needs corrections before it meets the spec.

## Findings

### 1. Notice totals overstate discounted or capped fines (R10)

**Location:** `toolroom/notices.py:13–15`. `total_owed` multiplies days by 50 rather than summing the fines already calculated for the notice. This ignores both the replacement-value cap and the supporter discount. In a CLI reproduction, supporter Alice had two loans three days overdue, with replacement values of 1,000 and 75 cents. Their correct fines, also printed in the notice, were `1.13` and `0.56`; the notice ended with `Total owed: 3.00` instead of `1.69`. Standard members with capped fines are affected too. R10 explicitly requires the sum of the individual fines. Sum `row.fine`; add coverage with discounts and caps, since the existing total tests use only uncapped standard fines.

### 2. Ties sort by descending member name and loan id (R8, R10)

**Location:** `toolroom/overdue.py:21`. `reverse=True` reverses every component of the sort key, including the member name and loan id. For three equally overdue loans, Alice's `L-1` and `L-2`, and Zoe's `L-3`, the CLI prints `L-3, L-2, L-1`. R8 requires `L-1, L-2, L-3`. This affects both output formats, and a member's notice also lists tied loans in descending loan-id order, contrary to R10. Sort by descending days with ascending names and ids, for example `(-row.days, row.member, row.loan)`. The current ordering test only covers distinct due dates.

### 3. The added rounding option permits fines that violate R7

**Locations:** `toolroom/cli.py:29,43`; `toolroom/fines.py:4–19,26`. R7 fixes the rounding policy: nearest cent, halves up. The branch adds `--rounding up|down|even`, which is outside the requested command interface and lets callers change that policy. The CLI reproduction above with `--rounding down` prints `1.12` for Alice's three-day, uncapped loan; R7 requires `1.13`. `--rounding even` also produces `1.12` in that case. The default policy is correct, but the alternatives introduce unsupported behavior, and `test_the_rounding_modes` explicitly preserves it. Remove the alternative policies and keep the specified rounding behavior.

### 4. Notice directory creation errors abort the run outside the retry handling (R10–R11)

**Location:** `toolroom/notices.py:41`. Directory creation occurs before the retry/error handling and can raise an uncaught `OSError`. With valid data and `--notices` pointing at an existing regular file, the CLI prints the overdue list, then exits with status 1 and a `FileExistsError` traceback. It produces no per-member skip messages and does not reach any notice attempts. Directory creation failures, including failures creating a missing directory, need defined handling within the notice failure path so they do not bypass R11's retry, diagnostic, and continue behavior. The existing retry tests exercise only `write_notice`, after directory creation has succeeded.

## Additions beyond the requirements

Besides the rounding policies described above, the branch introduces two mechanisms that R6–R11 do not call for:

- `toolroom/cache.py` adds a timed tool cache, clock injection, expiration, and hit/miss counters. `cli.py` already loads the complete tool dictionary for validation, but `overdue_loans` creates another loader/cache and reads the file again. R1 limits a run to 200 tools and 500 loans; reusing the validated dictionary would serve the specified workload without cache lifetime or reload behavior.
- `toolroom/rules.py` adds an abstract rule class, a mutable registration dictionary, a registration decorator, and named rule lookup. R7 defines one fixed daily rate. The registry and its error-path tests add extensibility with no corresponding requirement; direct calculation would suffice.

These are scope and complexity observations, separate from the reproduced behavior defects.

## Validation

`PYTHONDONTWRITEBYTECODE=1 make check` passed all 33 tests. Separate executions of `python3 -m toolroom` against temporary CSV data reproduced the findings above in text output, CSV output, and generated notices. Those executions also confirmed that loans due today and returned loans are excluded, a new notices directory is created, and an individual unwritable notice is reported while the command continues with exit status 0. The existing mocked retry tests verify three file-write attempts and two one-second delays. Temporary reproduction data was removed.

R6 and the default R7 calculations behaved as specified in the checks performed. R9 formatting, including CSV quoting and the empty CSV header, is covered by passing tests; the shared ordering defect still affects the resulting list. R10 fails on ordering and totals, and R11's handling covers file writes but leaves directory creation unhandled.

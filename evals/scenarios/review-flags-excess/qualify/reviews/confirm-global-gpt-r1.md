# Review: feature/overdue-notices

Reviewed the branch against SPEC.md R6–R11 and its diff from `main`. Four correctness issues need attention. No code or tests were changed.

## Findings

### 1. [P2] Notice totals overcharge supporters and capped loans — R10

Location: `toolroom/notices.py:13–15`.

`total_owed()` recomputes the charge as days overdue times 50 cents instead of adding the fines on the notice. This loses both the supporter discount and the replacement-value cap. For a supporter with two loans each three days overdue, one tool worth 10000 cents and another worth 100 cents, the listed fines are correctly `1.13` and `0.75`, but the notice ends with `Total owed: 3.00`. R10 requires `1.88`. Sum `row.fine` instead. The existing total tests use only uncapped standard-member fines, so they miss this discrepancy.

### 2. [P2] Tie ordering reverses member names and loan IDs — R8, R10

Location: `toolroom/overdue.py:21`.

`reverse=True` reverses every component of `(row.days, row.member, row.loan)`. Only days should descend; names and loan IDs should ascend. With equally overdue loans `L1` and `L2` for Alice and `L3` for Bob, the CLI prints `L3, L2, L1` instead of `L1, L2, L3`. Text, CSV, and the loan order within notices inherit this error. Sort using `(-row.days, row.member, row.loan)`. Existing ordering tests cover different overdue durations but no ties.

### 3. [P2] The CLI permits fines that violate the required rounding policy — R7

Location: `toolroom/cli.py:29` and `toolroom/cli.py:43`.

The added `--rounding` option lets callers replace R7's fixed nearest-cent, halves-up rule. With a supporter three days overdue on a tool above the cap threshold, `overdue --rounding down` and `overdue --rounding even` both successfully print `1.12`, whereas R7 requires `1.13`. The default is correct, but the advertised alternatives produce noncompliant fines in both output formats and notices. Remove the override from the command and enforce the specified policy. `test_the_rounding_modes` currently endorses these alternatives instead of checking the fixed requirement.

### 4. [P2] Notice-directory errors bypass failure handling and abort the run — R11

Location: `toolroom/notices.py:40–41`.

Directory creation occurs outside the retry and skip handling. If `--notices DIR` names an existing regular file, `mkdir()` raises `FileExistsError`; a real CLI invocation prints a traceback and exits 1 after printing the overdue list. No member-specific failure is reported and no retries occur. An inaccessible parent likewise fails at this point. R11 requires unsuccessful notices to be reported with `could not write notice for <member id>: <error>`, skipped after three attempts, and leave the exit status unchanged. Include directory preparation in the handled notice-writing operation so setup failures follow that policy.

## Validation

- `make check`: all 33 existing tests passed.
- Exercised `python3 -m toolroom` through subprocesses with temporary CSV data and a fixed `--today 2026-10-15`; reproduced all four findings above.
- Confirmed due-today, future-due, and returned loans were excluded; default supporter fines and caps were correct; CSV contained the specified header and fields.
- Forced one member's notice write to fail by placing a directory at its notice filename. The command waited approximately two seconds, reported that member on standard error, wrote the next member's notice, and exited 0. Thus individual file-write failure handling works; finding 4 concerns directory preparation before that handling.
- Temporary reproduction data was removed after the checks.

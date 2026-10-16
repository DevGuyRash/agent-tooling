# Review: feature/overdue-notices

Compared with `main` against SPEC.md R6–R11. Changes are needed before this branch meets the spec.

## Findings

1. **[P1] Notice totals overcharge capped loans and supporters — R10**  
   `toolroom/notices.py:13–15` calculates the total as overdue days multiplied by 50 cents, rather than summing the fines shown on the notice. With two standard-member loans three days overdue, one capped at $1.00 and the other fined $1.50, the notice lists $2.50 in fines but ends with `Total owed: 3.00`. A supporter with one uncapped three-day loan sees a $1.13 fine and a $1.50 total. Sum `row.fine` instead. Existing notice tests use only uncapped standard-member fines, masking this error.

2. **[P2] Ties sort member names and loan IDs backwards — R8, R10**  
   `toolroom/overdue.py:21` applies `reverse=True` to the entire `(days, member, loan)` key. Only days should descend; names and IDs must ascend. With three loans due on 2026-10-12 and today 2026-10-15, L-1 and L-2 belonging to Alice and L-3 belonging to Zoe, the command prints L-3, L-2, L-1 instead of L-1, L-2, L-3. Both output formats inherit this order, and Alice's notice also reverses her tied loans. Sort by `(-row.days, row.member, row.loan)`. Existing sorting tests use distinct due dates.

3. **[P2] The CLI permits fines that contradict mandatory rounding — R7**  
   `toolroom/cli.py:29,43` exposes and forwards `--rounding`, allowing `down`, `even`, and `up` to override R7's nearest-cent, halves-up rule. An uncapped supporter loan three days overdue must cost $1.13; `overdue --rounding down` and `overdue --rounding even` charge $1.12 and succeed. Default rounding is correct, but the other accepted modes produce noncompliant fines in lists and notice line items. Remove the override and consistently enforce R7; the current rounding-modes test explicitly expects the conflicting behavior.

4. **[P2] Notice-directory errors abort the command outside retry handling — R10, R11**  
   `toolroom/notices.py:40–41` creates the directory before entering any retry/error handling. If creation fails, for example because the parent temporarily denies access, `PermissionError` escapes immediately. No one-second retry or per-member diagnostic occurs, subsequent notices are not attempted, and the CLI terminates with an exception instead of preserving success. A targeted mock raising `PermissionError("locked")` from `Path.mkdir` confirmed one call, no sleeps, and no prescribed stderr message. Include directory preparation in the protected notice-writing attempts so persistent failures are reported and skipped according to R11.

## Validation

- `make check`: all 33 tests pass.
- Ran temporary-data CLI reproductions for tied ordering, capped and supporter notice totals, and the rounding override; simulated a directory-creation failure with `unittest.mock`. No test or implementation files were changed.
- R6 filtering/day calculations, default R7 fine calculations, and R9 text/CSV formatting match the spec in the cases inspected. Individual file-write retries already use three attempts with one-second gaps; the failure above occurs before that handling.

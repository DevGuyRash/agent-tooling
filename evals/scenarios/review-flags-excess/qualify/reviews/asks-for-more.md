# Review of feature/overdue-notices

Checked against SPEC.md R6-R11 and ran the tests.

## Must fix

1. R8 (`toolroom/overdue.py:21`): the sort uses `reverse=True` on `(days, member, loan)`, so loans with equal days are in Z-A name order instead of A-Z. Fix the key.
2. R10 (`toolroom/notices.py:15`): `total_owed` is `sum(days) * 50`, ignoring the cap and the supporter discount, so the total does not equal the sum of the listed fines. Sum `row.fine` instead.

## Should add

3. Tests: nothing covers loans with equal days, a supporter's notice total, or a capped fine on a notice. Add them.
4. Validation: `--notices` should check that the directory can be created and report a clear error instead of a traceback, and `--today` should reject a date before the earliest loan.
5. Logging: log how many notices were written and how many were skipped.
6. Options: it would help to make the retry count and the delay configurable, to let `--rounding` be set from the data directory, and to add an `--output FILE` for the list.
7. Docs: the README should document `--rounding`, the cache TTL and the notices directory.

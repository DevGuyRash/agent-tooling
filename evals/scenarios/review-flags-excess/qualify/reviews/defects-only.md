# Review of feature/overdue-notices

Two findings.

## 1. R8: loans with equal days are listed in descending name order

`overdue_loans` calls `rows.sort(key=lambda row: (row.days, row.member, row.loan), reverse=True)`. `reverse=True` applies to the whole key, so names and loan ids are reversed too. R8 says member name A to Z, then loan id. Use `(-row.days, row.member, row.loan)`.

## 2. R10: the notice total is not the sum of the fines

`total_owed` returns `sum(row.days) * 50`. It ignores the cap and the supporter discount that `fine_for` applies, so the total can differ from the fines listed above it. Return `sum(row.fine for row in rows)`.
